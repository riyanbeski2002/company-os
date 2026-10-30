"""Disposable worktrees, removed safely (directive V2 §13-19).

A task worktree is an execution resource, not storage: once its task is
terminal, everything worth keeping already lives somewhere cheaper — the
branch ref holds the commits, the event log holds the evidence. Before this
module, nothing ever removed a task worktree (MERGED left it on disk
forever), and the one removal that did exist — gategroup's rebuild — was
`git worktree remove --force` plus `rmtree`, which destroys uncommitted work
unconditionally.

The invariants (docs/HARNESS-AGNOSTIC-MIGRATION.md §4.3), every one of which
must hold or the worktree is reported, never forced:
  W1 ownership    a WORKTREE_CREATED event names this path (or, for worktrees
                  staffed before that event existed, it's named for a known
                  task and sits on that task's branch). A human's worktree is
                  invisible here.
  W2 containment  realpath strictly under .company/worktrees/, never the main
                  worktree — checked against git's own registration, so a
                  forged ownership record can't widen the reach.
  W3 no owner     no live worker, no fresh claim, no process with its cwd inside.
  W4 terminal     the task is DONE / MERGED / ABANDONED. FAILED is kept: it is
                  the state a retry resumes from.
  W5 clean        `git status` succeeds and shows nothing but what ensure_worktree
                  itself provisioned. A status that FAILS counts as dirty — the
                  ECC lifecycle this borrows from (worktree-lifecycle/git.js @
                  76aaa77, MIT) returned "clean" on error, the one bug not ported.
  W6 retained     commits stay reachable: branches are never deleted here, and
                  uncommitted changes or a detached HEAD are first written to
                  refs/company/checkpoints/* — beside the task branch, not on it.
  W7 git-native   `git worktree remove`; `--force` only after a checkpoint whose
                  tree was re-verified to equal the worktree's current content.
  W8 recorded     WORKTREE_REMOVED with the head SHA as evidence; a re-run finds
                  nothing to do, and a still-blocked worktree is logged once.

Staleness is never inferred from mtime (§16): a long-idle worktree whose
task is still IN_PROGRESS is kept however old it is.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import taskstate
from eventlog import EventLog, make_event, utcnow

MANAGED_DIR = "worktrees"
INTEGRATION_NAME = "_integration"  # integrate.py's long-lived merge target
SCRATCH_PREFIX = "_gate-group-"    # gategroup.py's per-review scratch
TERMINAL = {"DONE", "MERGED", "ABANDONED"}
CHECKPOINT_NS = "refs/company/checkpoints"

# Inherited from a git hook (or `git commit` running the pre-commit suite),
# these silently redirect every `git -C <worktree>` call at some other repo's
# index — the exact failure tools/git-hooks/pre-commit already had to scrub.
_GIT_SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
              "GIT_PREFIX", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")

_CHECKPOINT_IDENTITY = {
    "GIT_AUTHOR_NAME": "company-os", "GIT_AUTHOR_EMAIL": "company-os@localhost",
    "GIT_COMMITTER_NAME": "company-os", "GIT_COMMITTER_EMAIL": "company-os@localhost",
}


class _Blocked(Exception):
    pass


def _env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_SCRUB}
    env.update(extra)
    return env


def _git(cwd, *args, env: dict | None = None):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, env=env or _env())


def _real(p) -> str:
    return os.path.realpath(str(p))


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


# --- what git knows -----------------------------------------------------------

def list_worktrees(repo: Path) -> list[dict]:
    """`git worktree list --porcelain`, parsed. The first entry is the main
    worktree. Paths are realpath'd: macOS temp dirs alone (/var vs
    /private/var) would otherwise defeat every containment comparison."""
    r = _git(repo, "worktree", "list", "--porcelain")
    if r.returncode != 0:
        raise RuntimeError(f"git worktree list failed: {r.stderr.strip()}")
    out, cur = [], None
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            cur = {"path": _real(line[len("worktree "):]), "head": None, "branch": None,
                   "detached": False, "locked": False, "prunable": False}
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].removeprefix("refs/heads/")
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("locked"):
            cur["locked"] = True
        elif line.startswith("prunable"):
            cur["prunable"] = True
    return out


def _status(wt: Path) -> list[tuple[str, str]]:
    """(XY, path) entries, untracked files listed individually. Raises
    _Blocked if git can't answer — unknown is never treated as clean."""
    r = _git(wt, "status", "--porcelain", "--untracked-files=all", "-z")
    if r.returncode != 0:
        raise _Blocked(f"git status failed: {r.stderr.strip()[:200]}")
    tokens, entries, i = r.stdout.split("\0"), [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok:
            entries.append((tok[:2], tok[3:]))
            if tok[0] in "RC":
                i += 1  # a rename/copy's source path follows as its own token
        i += 1
    return entries


def _include_paths(repo: Path) -> set[str]:
    spec = Path(repo) / ".worktreeinclude"
    if not spec.exists():
        return set()
    out = set()
    for line in spec.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.update(str(p.relative_to(repo)) for p in Path(repo).glob(line) if p.is_file())
    return out


def _is_provisioned(repo: Path, wt: Path, rel: str, includes: set[str]) -> bool:
    """What worker.ensure_worktree itself put there (a loaded-skill symlink,
    a .worktreeinclude copy), still unchanged. Recognized by rule rather than
    a recorded list so worktrees staffed before this module existed qualify
    too. Anything a worker changed is no longer provisioned — it's work."""
    p, src = wt / rel, Path(repo) / rel
    if p.is_symlink():
        return src.is_symlink() and _real(src) == _real(p)
    if rel in includes and p.is_file() and src.is_file():
        return p.read_bytes() == src.read_bytes()
    return False


def _size(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def system_cwds() -> tuple[set[str] | None, str]:
    """Every process's current directory — how a human's shell or editor
    sitting inside a worktree (or a worker this module doesn't know about)
    is noticed. lsof first, tmux pane paths as the fallback; (None, ...) if
    neither can answer, which the report says plainly rather than implying
    the check ran."""
    if shutil.which("lsof"):
        try:
            r = subprocess.run(["lsof", "-n", "-d", "cwd", "-F", "n"],
                               capture_output=True, text=True, timeout=30)
            # lsof exits 1 whenever it couldn't inspect SOME process (another
            # user's); the rest of its output is still real.
            if r.stdout:
                return {l[1:] for l in r.stdout.splitlines() if l.startswith("n")}, "lsof"
        except (OSError, subprocess.SubprocessError):
            pass
    if shutil.which("tmux"):
        try:
            r = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{pane_current_path}"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return {_real(l) for l in r.stdout.splitlines() if l}, "tmux"
        except (OSError, subprocess.SubprocessError):
            pass
    return None, "unavailable"


# --- ownership and liveness -----------------------------------------------------

def record_created(company_root: Path, *, path: Path, branch: str, base: str | None,
                   task: str | None, project: str | None, reattached: bool) -> None:
    EventLog(company_root).append(make_event(
        event="WORKTREE_CREATED", actor="company", project=project or "_org",
        data={"path": str(path), "branch": branch, "base": base, "task": task,
              "reattached": reattached}))


def _live_owner(company_root: Path, tid: str) -> str | None:
    import worker  # lazy: worker imports this module to record ownership
    who = worker.live_worker_on(company_root, tid)
    if who:
        return f"live worker {who} is running in it"
    claim = Path(company_root) / "state" / "claims" / f"{tid}.claim"
    if claim.exists() and time.time() - claim.stat().st_mtime < worker.CLAIM_STALE_AFTER_S:
        return f"task is claimed by {claim.read_text(encoding='utf-8').strip()!r}"
    return None


def _classify(entry: dict, tasks: dict, created: dict) -> dict:
    path, name = entry["path"], Path(entry["path"]).name
    c = {"path": path, "name": name, "branch": entry["branch"], "head": entry["head"],
         "task": None, "project": None}
    if name == INTEGRATION_NAME:
        return {**c, "kind": "integration"}
    if name.startswith(SCRATCH_PREFIX) and entry["branch"] == name:
        return {**c, "kind": "scratch"}
    rec = created.get(path)
    tid = (rec or {}).get("data", {}).get("task")
    if rec is None and name in tasks and tasks[name].get("branch") == entry["branch"]:
        tid = name  # staffed before WORKTREE_CREATED existed
    if tid or rec:
        project = (tasks.get(tid) or {}).get("project") or (rec or {}).get("project")
        return {**c, "kind": "task", "task": tid, "project": project}
    return {**c, "kind": "unmanaged"}


# --- the decision ----------------------------------------------------------------

def _assess(repo, company_root, c, entry, tasks, includes, holders_fn) -> dict:
    """Fill in action (remove/keep/blocked), reasons, and what removal needs."""
    c.update(action="remove", reasons=[], dirty=False, provisioned=[])
    if c["kind"] == "integration":
        return {**c, "action": "keep", "reasons": ["integration worktree is permanent"]}
    if c["kind"] == "unmanaged":
        return {**c, "action": "keep", "reasons": ["not created by company-os"]}
    if entry["locked"]:
        return {**c, "action": "blocked", "reasons": ["worktree is locked"]}
    if c["kind"] == "task":
        status = (tasks.get(c["task"]) or {}).get("status")
        if status not in TERMINAL:
            return {**c, "action": "keep", "reasons": [f"task is {status or 'unknown'}"]}
        owner = _live_owner(company_root, c["task"])
        if owner:
            return {**c, "action": "blocked", "reasons": [owner]}
    cwds = holders_fn()
    if cwds and any(_inside(_real(h), c["path"]) for h in cwds):
        return {**c, "action": "blocked",
                "reasons": ["a process has its cwd inside this worktree"]}
    try:
        entries = _status(Path(c["path"]))
    except _Blocked as exc:
        return {**c, "action": "blocked", "reasons": [str(exc)]}
    for xy, rel in entries:
        if xy == "??" and _is_provisioned(repo, Path(c["path"]), rel, includes):
            c["provisioned"].append(rel)
        else:
            c["dirty"] = True
    return c


def _snapshot_tree(wt: Path, exclude: list[str]) -> str:
    """The worktree's full content (tracked + untracked, minus ignored and
    provisioned paths) as a tree object, built in a throwaway index so the
    worktree's own index and the repo's shared refs/stash are never touched."""
    with tempfile.TemporaryDirectory() as d:
        env = _env(GIT_INDEX_FILE=str(Path(d) / "index"))
        pathspec = ["--", "."] + [f":(exclude){p}" for p in exclude]
        for args in (("read-tree", "HEAD"), ("add", "-A", *pathspec)):
            r = _git(wt, *args, env=env)
            if r.returncode != 0:
                raise _Blocked(f"checkpoint failed at `git {args[0]}`: {r.stderr.strip()[:200]}")
        r = _git(wt, "write-tree", env=env)
        if r.returncode != 0:
            raise _Blocked(f"checkpoint failed at `git write-tree`: {r.stderr.strip()[:200]}")
        return r.stdout.strip()


def _checkpoint(c: dict) -> str:
    wt = Path(c["path"])
    if c["dirty"]:
        tree = _snapshot_tree(wt, c["provisioned"])
        r = _git(wt, "commit-tree", tree, "-p", "HEAD", "-m",
                 f"company-os checkpoint of {c['name']} before worktree removal",
                 env=_env(**_CHECKPOINT_IDENTITY))
        if r.returncode != 0:
            raise _Blocked(f"checkpoint failed at `git commit-tree`: {r.stderr.strip()[:200]}")
        commit = r.stdout.strip()
    else:
        commit = c["head"]  # detached and clean: only HEAD itself needs a ref
    stamp = utcnow().replace("-", "").replace(":", "")
    ref = f"{CHECKPOINT_NS}/{c['name']}-{stamp}-{commit[:12]}"
    # Empty old-value: create only, never overwrite an existing checkpoint.
    r = _git(wt, "update-ref", ref, commit, "")
    if r.returncode != 0:
        raise _Blocked(f"checkpoint ref not written: {r.stderr.strip()[:200]}")
    if c["dirty"] and _snapshot_tree(wt, c["provisioned"]) != tree:
        raise _Blocked(f"worktree changed while being checkpointed ({ref} kept)")
    return ref


def _remove(repo, company_root, c, *, trigger, actor) -> dict:
    wt = Path(c["path"])
    size = _size(wt)
    ref = None
    if c["dirty"] or c["branch"] is None:
        ref = _checkpoint(c)
    for rel in c["provisioned"]:
        (wt / rel).unlink()
    # --force only past a verified checkpoint (W7): what it discards is
    # exactly what `ref` now holds, plus ignored files (dependencies, the
    # .worktreeinclude copies) that were never meant to be kept.
    args = ["worktree", "remove", *(["--force"] if c["dirty"] else []), str(wt)]
    r = _git(repo, *args)
    if r.returncode != 0:
        raise _Blocked(f"git worktree remove refused: {r.stderr.strip()[:200]}")
    EventLog(company_root).append(make_event(
        event="WORKTREE_REMOVED", actor=actor, project=c["project"] or "_org",
        data={"path": c["path"], "kind": c["kind"], "task": c["task"], "branch": c["branch"],
              "trigger": trigger, "bytes_reclaimed": size, "checkpoint": ref},
        evidence={"commit": c["head"]}))
    return {"path": c["path"], "kind": c["kind"], "task": c["task"], "branch": c["branch"],
            "bytes": size, "checkpoint": ref}


def _record_blocked(company_root, events, c, *, trigger, actor) -> None:
    """Log a blocked worktree once per distinct reason set, not every sweep."""
    for ev in reversed(events):
        if (ev.get("event") in ("WORKTREE_CREATED", "WORKTREE_REMOVED",
                                "WORKTREE_CLEANUP_BLOCKED")
                and _real((ev.get("data") or {}).get("path", "")) == c["path"]):
            if (ev["event"] == "WORKTREE_CLEANUP_BLOCKED"
                    and ev["data"].get("reasons") == c["reasons"]):
                return
            break
    EventLog(company_root).append(make_event(
        event="WORKTREE_CLEANUP_BLOCKED", actor=actor, project=c.get("project") or "_org",
        data={"path": c["path"], "kind": c["kind"], "task": c.get("task"),
              "reasons": c["reasons"], "trigger": trigger}))


def cleanup(repo: Path, company_root: Path, *, task: str | None = None,
            only_path: Path | None = None, dry_run: bool = False,
            trigger: str = "manual", actor: str = "company", holders=None) -> dict:
    """Reconcile managed worktrees against the event log. `task` or
    `only_path` narrows the sweep (lifecycle triggers); with neither, it is
    the full reconciliation, which also reports unregistered directories and
    prunes git's records of worktrees that vanished from disk.

    `holders` returns the set of process cwds (or None if unknown); injected
    by tests, defaulting to system_cwds(), called at most once and only if
    some worktree is otherwise removable."""
    repo, company_root = Path(repo), Path(company_root)
    managed = _real(company_root / MANAGED_DIR)
    log = EventLog(company_root)
    events = log.read()
    tasks = taskstate.fold(events)
    created = {_real(e["data"]["path"]): e for e in events
               if e.get("event") == "WORKTREE_CREATED" and (e.get("data") or {}).get("path")}
    includes = _include_paths(repo)

    probe = {"how": "not_needed"}
    cache: list = []

    def holders_fn():
        if not cache:
            if holders is not None:
                cache.append(holders())
                probe["how"] = "injected"
            else:
                cwds, how = system_cwds()
                cache.append(cwds)
                probe["how"] = how
        return cache[0]

    entries = list_worktrees(repo)
    main = entries[0]["path"] if entries else _real(repo)
    report = {"dry_run": dry_run, "trigger": trigger, "removed": [], "blocked": [],
              "kept": [], "pruned": False, "prunable": [], "bytes_reclaimed": 0}
    want = _real(only_path) if only_path is not None else None

    for entry in entries:
        if entry["path"] == main or not _inside(entry["path"], managed) \
                or entry["path"] == managed or entry["prunable"]:
            continue  # W2: never the main worktree, never outside our root
        if want is not None and entry["path"] != want:
            continue
        c = _classify(entry, tasks, created)
        if task is not None and c["task"] != task:
            continue
        c = _assess(repo, company_root, c, entry, tasks, includes, holders_fn)
        summary = {"path": c["path"], "kind": c["kind"], "task": c["task"],
                   "reasons": c["reasons"]}
        if c["action"] == "keep":
            report["kept"].append(summary)
            continue
        if c["action"] == "remove" and dry_run:
            report["removed"].append({"path": c["path"], "kind": c["kind"], "task": c["task"],
                                      "branch": c["branch"], "bytes": _size(Path(c["path"])),
                                      "checkpoint": None,
                                      "would_checkpoint": c["dirty"] or c["branch"] is None})
            continue
        if c["action"] == "remove":
            try:
                report["removed"].append(_remove(repo, company_root, c,
                                                 trigger=trigger, actor=actor))
                continue
            except _Blocked as exc:
                c.update(action="blocked", reasons=[str(exc)])
                summary["reasons"] = c["reasons"]
        report["blocked"].append(summary)
        if not dry_run:
            _record_blocked(company_root, events, c, trigger=trigger, actor=actor)

    if task is None and want is None:
        _reconcile_disk(company_root, managed, entries, report, events, dry_run, trigger, actor)
        prunable = [e["path"] for e in entries if e["prunable"]]
        report["prunable"] = prunable
        # `git worktree prune` has no path filter: run it only when every
        # vanished worktree is one of ours, so a user's worktree on an
        # unmounted drive keeps its registration.
        if prunable and not dry_run and all(_inside(p, managed) for p in prunable):
            report["pruned"] = _git(repo, "worktree", "prune").returncode == 0

    report["bytes_reclaimed"] = sum(r["bytes"] for r in report["removed"])
    report["holders_check"] = probe["how"]
    return report


def _reconcile_disk(company_root, managed, entries, report, events, dry_run, trigger, actor):
    """Directories under the managed root that git doesn't know as worktrees:
    an empty one is removed (rmdir can't destroy content); anything else is
    reported for a human — it may be someone's work, and it isn't ours to
    judge by deletion."""
    root = Path(managed)
    if not root.is_dir():
        return
    registered = {e["path"] for e in entries}
    for child in sorted(root.iterdir()):
        path = _real(child)
        if not child.is_dir() or child.is_symlink() or path in registered:
            continue
        if not any(child.iterdir()):
            if not dry_run:
                child.rmdir()
            continue
        c = {"path": path, "kind": "unregistered", "task": None,
             "reasons": ["directory is not a registered git worktree; left for manual review"]}
        report["blocked"].append(dict(c))
        if not dry_run:
            _record_blocked(company_root, events, c, trigger=trigger, actor=actor)


def cleanup_path(repo: Path, company_root: Path, path: Path, *, trigger: str,
                 actor: str = "company", holders=None) -> dict:
    return cleanup(repo, company_root, only_path=path, trigger=trigger,
                   actor=actor, holders=holders)


def remove_scratch(repo: Path, company_root: Path, path: Path) -> None:
    """For gategroup's rebuild: the old scratch must actually be gone before
    a fresh one is built at the same path. Raises with the reason otherwise —
    never falls back to deleting it some other way."""
    report = cleanup_path(repo, company_root, path, trigger="rebuild")
    if Path(path).exists():
        reasons = [r for b in report["blocked"] for r in b["reasons"]] \
            or ["not a registered company-os worktree"]
        raise RuntimeError(f"could not remove the previous review worktree {path}: "
                           + "; ".join(reasons))
