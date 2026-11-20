"""Tier-2 worker lifecycle: worktree, launch, supervise, record (D2, D7).

A worker is a `claude -p` process we own. We get an exit code, a session id,
and a parseable result — which is the whole reason this tier exists rather than
`--bg`. A background session looks nicer and returns nothing checkable, and the
Evidence Rule is made of checkable things.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from eventlog import EventLog, EvidenceError, make_event
import gatesig
import harness
import providers
import staffing

PLUGIN_ROOT = Path(__file__).resolve().parents[2]


def launch_plugin_root(repo: Path) -> Path:
    """The --plugin-dir a writing worker on `repo` is launched with.

    Claude Code refuses every Write/Edit to a file under the loaded plugin
    directory ("... which is a sensitive file", no override in headless mode).
    When company-os works on itself the plugin dir IS the repo, and every
    task worktree (.company/worktrees/) sits inside it, so a self-hosted
    worker could edit nothing. Bisected live on claude 2.1.322, 2026-11-10:
    same worktree and flags, --plugin-dir <repo> refused, --plugin-dir <copy
    outside the repo> wrote (this is what ESC-009 actually was).

    So a self-hosted launch gets a read-only export of the committed HEAD,
    outside the repo — the same commit its worktree branches from, so the
    worker runs under the hooks and personas that were reviewed, never ones
    edited mid-task. external/ (gitignored, clone-only) is linked through,
    since workers read capability repos via $CLAUDE_PLUGIN_ROOT/external.
    Any other repo is not inside the plugin dir and keeps PLUGIN_ROOT.
    """
    if Path(repo).resolve() != PLUGIN_ROOT:
        return PLUGIN_ROOT
    import shutil
    import tempfile
    sha = subprocess.run(["git", "-C", str(PLUGIN_ROOT), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    parent = cache / "company-os" / "plugin"
    dest = parent / sha
    if (dest / ".complete").exists():
        return dest
    parent.mkdir(parents=True, exist_ok=True)
    _prune_plugin_snapshots(parent, keep=sha)
    tmp = Path(tempfile.mkdtemp(dir=parent, prefix=f"{sha}.tmp-"))  # unique: never reused
    archive = subprocess.run(["git", "-C", str(PLUGIN_ROOT), "archive", sha],
                             capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive, check=True)
    ext = tmp / "external"
    if ext.exists() and not ext.is_symlink():
        shutil.rmtree(ext)  # the archive carries only external/README.md
    ext.symlink_to(PLUGIN_ROOT / "external")
    (tmp / ".complete").write_text(sha + "\n")
    _make_read_only(tmp)
    try:
        tmp.rename(dest)
    except OSError:  # a concurrent launch finished first; theirs is identical
        _remove_tree(tmp)
    return dest


def _make_read_only(root: Path) -> None:
    """Strip write bits from the snapshot (files and dirs; the external/
    symlink itself is left alone, its target is the live clone)."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames + dirnames:
            path = Path(dirpath) / name
            if not path.is_symlink():
                path.chmod(path.stat().st_mode & ~0o222)
    root.chmod(root.stat().st_mode & ~0o222)


def _remove_tree(root: Path) -> None:
    """rmtree a snapshot made read-only by _make_read_only."""
    import shutil
    for dirpath, dirnames, _ in os.walk(root):
        for name in dirnames:
            p = Path(dirpath) / name
            if not p.is_symlink():
                p.chmod(p.stat().st_mode | 0o700)
    root.chmod(root.stat().st_mode | 0o700)
    shutil.rmtree(root, ignore_errors=True)


SNAPSHOTS_KEPT = 5           # recent HEADs a still-running worker may be using
STALE_TMP_AFTER_S = 86400    # an unfinished export this old is a crashed launch


def _prune_plugin_snapshots(parent: Path, keep: str) -> None:
    """Bound the cache: drop crashed exports older than a day, and all but
    the newest SNAPSHOTS_KEPT finished snapshots (never `keep`)."""
    now = time.time()
    done = []
    for entry in parent.iterdir():
        if ".tmp-" in entry.name:
            if now - entry.stat().st_mtime > STALE_TMP_AFTER_S:
                _remove_tree(entry)
        elif entry.name != keep and (entry / ".complete").exists():
            done.append(entry)
    done.sort(key=lambda e: e.stat().st_mtime, reverse=True)
    for old in done[SNAPSHOTS_KEPT - 1:]:
        _remove_tree(old)


# Structured output contract. Forcing a schema means the worker's report is
# parsed, not interpreted.
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "commit": {"type": "string"},
        "tests_command": {"type": "string"},
        "tests_exit_code": {"type": "integer"},
        "contract_published": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "blocked_reason": {"type": "string"},
        # Gate roles only (ESC-002): the verdict itself. The launcher, not
        # the worker, turns it into the signed *_PASSED/*_FAILED event. A
        # solo gate may use `verdict`; a gate group answers per task.
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "findings": {"type": "array", "items": {"type": "string"}},
        "criteria_met": {"type": "array", "items": {"type": "string"}},
        "task_verdicts": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "verdict": {"type": "string", "enum": ["pass", "fail"]},
                "findings": {"type": "array", "items": {"type": "string"}},
                "criteria_met": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task", "verdict"],
        }},
    },
    "required": ["summary", "blocked"],
}

# Deliberately narrower than the matching agent/*.md `tools:` line, which also
# lists ListAgents/SendMessage for the interactive-tmux-pane case (see
# agents/company-pm.md, "Coordinating with other sessions"). A headless run
# has nobody watching to receive a ping and no legitimate reason to reach
# outside its own worktree, so this dict — not the frontmatter — is what
# `--allowedTools` is actually built from below, and it stays fixed at the
# original six-or-fewer tools. Keep it that way; widening this dict is a real
# increase in a headless worker's reach, not just a documentation update.
ROLE_TOOLS = {
    "backend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "frontend-engineer": "Read,Grep,Glob,Edit,Write,Bash",
    "video-editor": "Read,Grep,Glob,Edit,Write,Bash",
    "code-reviewer": "Read,Grep,Glob,Bash",
    "qa-engineer": "Read,Grep,Glob,Bash",
    "security-reviewer": "Read,Grep,Glob,Bash",
}

# KNOWN_ISSUES #3: security-reviewer-201 ran 11 clean turns and emitted
# neither SECURITY_REVIEW_PASSED nor SECURITY_REVIEW_FAILED. The gate was
# silently re-run under a new actor name, paying for the review twice — a
# reviewer ending cleanly with no verdict looked identical to success. The
# fix below makes that impossible to miss: if a gate role's worker exits
# without a matching verdict event, that is GATE_NO_VERDICT, not "done."
# NOTE: also the sandbox's network policy — every role listed here gets
# localhost access (sandbox_settings, ESC-013). Adding a role widens that.
GATE_VERDICT_EVENTS = {
    "code-reviewer": ("REVIEW_PASSED", "REVIEW_FAILED"),
    "qa-engineer": ("QA_PASSED", "QA_FAILED"),
    "security-reviewer": ("SECURITY_REVIEW_PASSED", "SECURITY_REVIEW_FAILED"),
}


class WorkerError(RuntimeError):
    pass


def gave_no_verdict(events: list[dict], task_id: str, actor: str, role: str) -> tuple | None:
    """None if the actor emitted its gate's verdict on this task; otherwise
    the (pass_event, fail_event) pair it was expected to emit. Pure and
    testable on purpose — the launch() call site can't be unit-tested without
    a real subprocess, this can."""
    pair = GATE_VERDICT_EVENTS.get(role)
    if not pair:
        return None
    pass_ev, fail_ev = pair
    for ev in events:
        if ev.get("task") == task_id and ev.get("actor") == actor \
                and ev.get("event") in (pass_ev, fail_ev):
            return None
    return pair


def _gate_key(company_root: Path, role: str) -> bytes | None:
    """The launcher's verdict-signing key for a gate role, created on first
    use (ESC-002). Never put in a worker's env or argv."""
    if role not in GATE_VERDICT_EVENTS:
        return None
    try:
        return gatesig.load_key(company_root, create=True)
    except OSError as exc:
        raise WorkerError(f"cannot create the gate signing key: {exc}") from exc


def branch_sha(repo: Path, branch: str | None) -> str:
    """The SHA a gate judges: the task branch's tip, read through the main
    checkout before launch. Signed into the launch and the verdict, and what
    integrate merges — later commits to the branch are never reviewed."""
    r = _git_trusted(repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
                     f"refs/heads/{branch}^{{commit}}", capture_output=True, text=True)
    sha = r.stdout.strip()
    if not branch or r.returncode != 0 or not sha:
        raise WorkerError(f"cannot read the tip of branch {branch!r} to review")
    return sha


def record_verdicts(log: EventLog, gate_key: bytes, role: str, actor: str, project: str,
                    ws_seq: int, tasks: list[dict], result: dict, exit_code: int | None,
                    out_path: Path, commits: dict[str, str],
                    group_id: str | None = None) -> list[str]:
    """After a gate worker exits: append the signed verdict event its
    structured output gave for each task (ESC-002), or GATE_NO_VERDICT.
    A pass from a run that errored is not a verdict. `commits` is what the
    launch signed (task -> SHA). Returns the task ids left without one."""
    pass_ev, fail_ev = GATE_VERDICT_EVENTS[role]
    ids = [t["id"] for t in tasks]
    verdicts = gatesig.structured_verdicts(result.get("structured_output"), ids)
    ran_clean = exit_code == 0 and not result.get("is_error")
    extra = {"gate_group": group_id} if group_id else {}
    missing = []
    for t in tasks:
        v = verdicts.get(t["id"])
        if v and (v["verdict"] == "fail" or ran_clean):
            event = pass_ev if v["verdict"] == "pass" else fail_ev
            commit = commits[t["id"]]
            evidence = {"log": str(out_path), "commit": commit}
            data = {"role": role, "ws_seq": ws_seq, "verdict": v["verdict"], "commit": commit,
                    "verdict_mac": gatesig.verdict_mac(gate_key, t["id"], event, actor,
                                                       role, ws_seq, v["verdict"], commit),
                    "source": "structured_output", **extra}
            for k in ("findings", "criteria_met"):
                if v[k]:
                    data[k] = v[k]
            try:
                log.append(make_event(event=event, actor=actor, project=project,
                                      task=t["id"], data=data, evidence=evidence))
                continue
            except EvidenceError as exc:  # e.g. a PASS on the commit it already failed
                reason = str(exc)
        else:
            reason = None
        if v is None and any(e.get("event") == fail_ev and e.get("task") == t["id"]
                             and e.get("actor") == actor for e in log.read()):
            continue  # the worker recorded its own FAILED: still a verdict. Its
            # own PASSED never is — anything in its process tree can write one.
        missing.append(t["id"])
        log.append(make_event(
            event="GATE_NO_VERDICT", actor=actor, project=project, task=t["id"],
            data={"role": role, "expected_one_of": [pass_ev, fail_ev],
                  "exit_code": exit_code, "is_error": result.get("is_error"),
                  "terminal_reason": result.get("terminal_reason"),
                  **({"reason": reason} if reason else {}), **extra},
        ))
    return missing


def slug(text: str, limit: int = 32) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:limit].strip("-") or "task"


# --- worktree ---------------------------------------------------------------

def ensure_worktree(repo: Path, company_root: Path, task: dict) -> tuple[Path, str]:
    """Create the task's worktree and branch. Never removes an existing one.

    Records WORKTREE_CREATED — the ownership fact worktrees.cleanup needs
    before it may ever remove this directory. Once a task's worktree has been
    cleaned up its branch still exists, so a later call (a gate re-diffing a
    merged task) re-attaches that branch instead of failing on `-b`."""
    import worktrees
    tid = task["id"]
    branch = task.get("branch") or f"task/{tid.split('-')[-1]}-{slug(task.get('title', tid))}"
    wt = Path(task.get("worktree") or (company_root / "worktrees" / tid))

    if wt.exists():
        if not (wt / ".git").exists():
            # A directory with no .git is not a worktree: every git command a
            # worker runs inside it resolves to the MAIN checkout (gategroup.py's
            # 2026-09-09 incident). Refuse rather than launch into it.
            raise WorkerError(
                f"{wt} exists but is not a git worktree — a worker launched there "
                f"would operate on the main checkout. Inspect it; `company cleanup "
                f"--dry-run` reports it.")
        return wt, branch  # preserved from a previous run, by design

    base = task.get("base") or _default_base(repo)
    wt.parent.mkdir(parents=True, exist_ok=True)
    reattach = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True, text=True).returncode == 0
    add = [str(wt), branch] if reattach else [str(wt), "-b", branch, base]
    r = subprocess.run(["git", "-C", str(repo), "worktree", "add", *add],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise WorkerError(f"git worktree add failed: {r.stderr.strip()}")
    worktrees.record_created(company_root, path=wt, branch=branch, base=base, task=tid,
                             project=task.get("project"), reattached=reattach)

    _copy_worktree_includes(repo, wt)
    _link_loaded_skills(repo, wt)
    return wt, branch


def _default_base(repo: Path) -> str:
    for ref in ("main", "master"):
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", ref],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    return "HEAD"


def _copy_worktree_includes(repo: Path, wt: Path) -> None:
    """Carry gitignored local config into the worktree.

    Claude Code does this for worktrees it creates itself; ours are plain git
    worktrees, so we do it here.
    """
    spec = repo / ".worktreeinclude"
    if not spec.exists():
        return
    for line in spec.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for src in repo.glob(line):
            if src.is_file():
                dst = wt / src.relative_to(repo)
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())


def _link_loaded_skills(repo: Path, wt: Path) -> None:
    """Carry currently-`load`ed capability skills (tools/capability.py) into
    the worktree, same reasoning as _copy_worktree_includes: Claude Code's own
    skill-discovery scans the *worktree's* skills/, not the main checkout's,
    so a worker otherwise can't see a skill loaded in the main checkout even
    though it CAN already read anything under external/ (that's resolved via
    $CLAUDE_PLUGIN_ROOT: the main checkout, or — when company-os works on
    itself — a committed snapshot whose external/ links back to the main
    checkout's; see launch_plugin_root. Uncommitted config/registry edits
    are therefore invisible to self-hosted workers until committed).

    skills/<id> entries created by `capability.py load` are symlinks into
    external/<id>/... (itself gitignored, main-checkout-only); we recreate
    the same symlink, pointing at the *main repo's* absolute path, so the
    worktree doesn't need its own external/ clone.
    """
    src_skills = repo / "skills"
    if not src_skills.is_dir():
        return
    dst_skills = wt / "skills"
    for entry in src_skills.iterdir():
        if not entry.is_symlink():
            continue  # vendored real skills (e.g. skills/claudedesignskills/) are
                      # tracked in git and already present via the worktree checkout
        target = entry.resolve()
        dst = dst_skills / entry.name
        if dst.exists() or dst.is_symlink():
            continue
        dst_skills.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(target)


# --- launch -----------------------------------------------------------------

# The .company/ subdirectories a sandboxed worker's own `company` CLI calls
# write to (event, handoff, escalate, session ping, and the task/goal/
# escalation views taskstate.rebuild() regenerates after each event) — read
# off cli.py/eventlog.py/taskstate.py/goals.py/escalations.py/sessions.py,
# not guessed. Everything else under .company/ (worktrees of OTHER tasks,
# config, state/workers' pid files) stays unwritable.
SANDBOX_WRITABLE = ("events", "tasks", "goals", "handoffs", "escalations", "state/sessions")

# A third-party report describes Seatbelt write policies widening when a
# workspace path contains glob syntax. Claude Code 2.1.308 documents that it
# ignores glob-spelled allowWrite values, but the launch cwd is granted
# implicitly, so validate every path rather than trust either behavior.
_GLOB_CHARS = set("*?[]{}")


def sandbox_settings(company_root: Path, workdir: Path,
                     role: str | None = None) -> dict:
    """Per-launch Claude Code sandbox policy (passed via `--settings`).

    The sandbox confines every Bash call — and every child it spawns:
    `python3 -c`, `cd ../..`, raw appends — at the OS level, which the
    command-string regexes in hooks/protect_branches.py cannot. Writes are
    allowed only in `workdir` (the launch cwd, which Claude Code grants
    implicitly; it also grants a worktree's own git metadata so commits
    work) plus SANDBOX_WRITABLE. .company/secrets is unreadable from Bash
    (guard_secrets.py only covers the Read/Grep tools).

    failIfUnavailable + allowUnsandboxedCommands=false are the load-bearing
    pair: Bash is pre-allowed for every worker, so a sandbox that failed to
    start, or a model retrying with dangerouslyDisableSandbox, would
    otherwise run with no containment at all.
    """
    company_root = Path(company_root).resolve()
    writable = [company_root / d for d in SANDBOX_WRITABLE]
    secrets = company_root / "secrets"
    for path in (Path(workdir).resolve(), *writable, secrets):
        if _GLOB_CHARS & set(str(path)):
            raise WorkerError(
                f"refusing to launch: sandbox path {str(path)!r} contains glob "
                f"characters, which could widen the sandbox's write policy")
    for path in writable:
        # A not-yet-existing allowWrite dir can't be created from inside the
        # sandbox (its parent isn't writable), so make them all up front.
        path.mkdir(parents=True, exist_ok=True)
    policy = {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "filesystem": {
            "allowWrite": [str(p) for p in writable],
            "denyRead": [str(secrets)],
        },
    }
    if role in GATE_VERDICT_EVENTS:
        # ESC-013 (trade-ai, resolved by Riyan 2026-10-27, option 1).
        # Gate roles run the project's REAL test suite, which on some repos
        # includes a Postgres lane against a local container. The sandbox
        # blocks that TCP connect, so QA was silently passing on the SQLite
        # lane only and never verifying Postgres-specific behaviour
        # (locking, triggers, migrations) — the exact class of bug
        # trade-ai TASK-206 had to fix.
        #
        # Live-tested on claude 2.1.310, three runs:
        #   no network key                  -> connect() EPERM  (the bug)
        #   network.allowedDomains ["127.0.0.1:5433"] -> STILL EPERM, because
        #       allowedDomains governs PROXIED HTTP; a DB driver's raw socket
        #       never consults it. A per-port localhost allow does not exist.
        #   network.allowLocalBinding true  -> localhost reachable,
        #       example.com:80 still fails DNS. Internet stays blocked.
        #
        # So this is all-of-localhost or nothing. Scoped to GATE roles only:
        # implementers, who write the code, stay fully network-sandboxed.
        # Filesystem containment is untouched (independent layer).
        # Accepted residual risk: a gate worker can reach other local
        # services, so the failure mode is misleading evidence, not damage.
        policy["network"] = {"allowLocalBinding": True}
    # --setting-sources loads the worktree's own .claude/settings*.json, which
    # the implementer can commit; `disableAllHooks: true` there would switch
    # off every guard. --settings outranks project and local settings.
    return {"sandbox": policy, "disableAllHooks": False}


def build_env(repo: Path, company_root: Path, task: dict, actor: str,
              worktree: Path, thinking: bool = True,
              harness_spec: dict | None = None, allowed_tools: str | None = None,
              plugin_root: Path | None = None, extra_env: dict | None = None) -> dict:
    """Build the worker's environment.

    COMPANY_REPO is the *worktree*, not the main checkout: the worker's whole
    world is its worktree, so owned globs like `api/approvals/**` must resolve
    against it. Pointing this at the main checkout makes every path look like
    `.company/worktrees/TASK-101/api/...` and blocks the worker from its own
    files.

    Vendor-specific env stripping (a stale ANTHROPIC_API_KEY silently
    overriding the claude.ai login, the parent session's own identity
    leaking into the child) is the harness's own policy now, not hardcoded
    here — see config/harness.yaml's `strip_env`. A harness_spec of None
    resolves the configured default, so existing callers that built env
    before a role/harness was known keep working unchanged.
    """
    env = dict(os.environ)
    spec = harness_spec or harness.resolve(harness.load_config(company_root), None)
    env = harness.apply_env(spec, env)
    if spec.get("_provider"):
        # A non-native provider (providers.yaml): its key travels only in the
        # variable the harness declares, never under its own key_ref name.
        add, remove = providers.worker_env(spec["_provider"], spec)
        for var in remove:
            env.pop(var, None)
        env.update(add)
    if extra_env:
        # gate_services output (start_gate_services). Applied before the
        # COMPANY_* block so it can never override company-os's own vars.
        env.update(extra_env)

    env.update({
        "COMPANY_TASK": task["id"],
        "COMPANY_ACTOR": actor,
        "COMPANY_ROOT": str(company_root),
        "COMPANY_REPO": str(worktree),
        "COMPANY_MAIN_REPO": str(repo),
        "COMPANY_PROJECT": task.get("project", ""),
        "PATH": f"{PLUGIN_ROOT / 'bin'}:{env.get('PATH', '')}",
    })
    if plugin_root is not None:
        # The --plugin-dir this worker was launched with (a snapshot on
        # self-hosted launches, see launch_plugin_root) — the shell guard
        # allows `cd` into it the same way it allows the main repo.
        env["COMPANY_PLUGIN_ROOT"] = str(plugin_root)
    if allowed_tools is not None:
        # The role's tool restriction, for hooks/guard.py: Claude Code enforces
        # an agent file's `tools:` natively, but a harness that gets the persona
        # inlined loses that frontmatter — this is how its shim still knows a
        # reviewer is read-only.
        env["COMPANY_ALLOWED_TOOLS"] = allowed_tools
    if not thinking:
        # No CLI flag for thinking exists (checked `claude -p --help`,
        # v2.1.239) — MAX_THINKING_TOKENS=0 is the actual lever, reserved for
        # mechanical, ungated work where thinking is pure cost (D11 / §2,
        # efficiency addendum v1).
        env["MAX_THINKING_TOKENS"] = "0"
    return env


# ---------------------------------------------------------------------------
# gate_services (finos ESC-239, option A, Riyan 2026-11-19)
#
# A gate role that must run a database-backed suite can't start the database
# itself: its sandbox blocks Docker. The project declares the services in
# .company/config/project.yaml instead, and company-os brings them up OUTSIDE
# the sandbox before the gate launches and tears them down afterwards:
#
#   gate_services:
#     - up: "bash scripts/verify-db-up.sh"
#       env_from_output: {SECURITY_TEST_DATABASE_URL: 'SECURITY_TEST_DATABASE_URL=(\S+)'}
#       down: "bash scripts/verify-db-up.sh --stop"
#       timeout_s: 600          # optional, applies to up and down separately
#
# Trust boundary: up/down run with cwd = the project's MAIN checkout, and the
# config is read from the main checkout's .company/ — never from the gate's
# worktree. The worktree is the branch under review; running its scripts
# unsandboxed (with Docker) would hand any implementer root-equivalent
# execution. The script gets the branch as DATA only: COMPANY_GATE_WORKTREE
# is a snapshot of the reviewed branch's commit, read through the MAIN
# repo's gitdir (never the worktree's own .git, which the implementer can
# repoint), regular files only — so a planted link can't make the
# unsandboxed script read (and echo) ~/.ssh or .company/secrets.
#
# - Only stdout is parsed, and the FIRST match wins: anything the branch can
#   make the script print comes after the script's own line.
# - Command output is logged under .company/secrets/ (denied to every
#   sandboxed worker): it can carry credentials. Events carry var NAMES only.
# - The command strings themselves do go into events: keep secrets out of
#   them (read them from a file or env inside the script instead).
# ---------------------------------------------------------------------------

_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
# Injected after the harness's strip_env and the provider's key vars, so a
# name here could re-add a stripped credential, retarget the model provider,
# or hijack the worker's interpreter/loader/shell. Trusted config or not,
# none of these is a service endpoint.
_RESERVED_ENV = re.compile(
    r"^(COMPANY_|ANTHROPIC_|CLAUDE_|OPENAI_|CODEX_|GEMINI_|GOOGLE_|AWS_|LD_|DYLD_|"
    r"PYTHON|NODE_|NPM_|GIT_|SSH_|BUN_)|^(PATH|HOME|SHELL|USER|TMPDIR|ENV|BASH_ENV|"
    r"MAX_THINKING_TOKENS|VERIFY_ID|IFS|PS4|SSL_CERT_FILE|SSL_CERT_DIR|"
    r"JAVA_TOOL_OPTIONS|RUBYOPT|[A-Z_]*_PROXY)$|^(BASH_FUNC_|PERL5)")
GATE_SERVICE_TIMEOUT = 600


def _service_id(raw: str) -> str:
    """A VERIFY_ID safe as a docker compose project name / path segment."""
    return re.sub(r"[^a-z0-9_-]+", "-", raw.lower()).strip("-_") or "gate"


def load_gate_services(company_root: Path) -> list[dict]:
    """The validated `gate_services` list, or [] when none is declared. A
    malformed entry is a WorkerError: a gate silently launched without the
    services it was configured to have would just report UNVERIFIED."""
    try:
        cfg = staffing.load_config(company_root, "project.yaml")
    except FileNotFoundError:
        return []
    services = cfg.get("gate_services") or []
    if not isinstance(services, list):
        raise WorkerError("project.yaml gate_services must be a list")
    out = []
    for i, svc in enumerate(services):
        where = f"project.yaml gate_services[{i}]"
        if not isinstance(svc, dict) or not isinstance(svc.get("up"), str) or not svc["up"].strip():
            raise WorkerError(f"{where} needs an `up` command string")
        if svc.get("down") is not None and not isinstance(svc["down"], str):
            raise WorkerError(f"{where}: `down` must be a command string")
        patterns = svc.get("env_from_output") or {}
        if not isinstance(patterns, dict):
            raise WorkerError(f"{where}: env_from_output must map VAR: regex")
        compiled = {}
        for var, pat in patterns.items():
            if not isinstance(var, str) or not _ENV_NAME.match(var) \
                    or _RESERVED_ENV.match(var):
                raise WorkerError(f"{where}: {var!r} is not an injectable env var name")
            try:
                rx = re.compile(str(pat))
            except re.error as exc:
                raise WorkerError(f"{where}: bad regex for {var}: {exc}") from None
            if rx.groups != 1:
                raise WorkerError(f"{where}: regex for {var} needs exactly one capture group")
            compiled[var] = rx
        timeout = svc.get("timeout_s", GATE_SERVICE_TIMEOUT)
        if not isinstance(timeout, int) or timeout <= 0:
            raise WorkerError(f"{where}: timeout_s must be a positive integer")
        out.append({"up": svc["up"], "down": svc.get("down"),
                    "env_from_output": compiled, "timeout_s": timeout})
    return out


def _run_service_cmd(cmd: str, repo: Path, env: dict, timeout: int, log_path: Path) -> tuple:
    """(exit_code or None on timeout, stdout). Both streams go to log_path,
    never into an event: they can carry credentials."""
    # Own process group: on timeout the whole tree dies (a `docker compose
    # up --wait` under the script), not just the shell.
    proc = subprocess.Popen(cmd, shell=True, cwd=str(repo), env=env, text=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        code = None
    except BaseException:  # SIGTERM-as-SystemExit, Ctrl-C: don't leave it running
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise
    out, err = out or "", err or ""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"$ {cmd}\n--- stdout\n{out}\n--- stderr\n{err}\n[exit {code}]\n")
    return code, out


def _git_trusted(repo: Path, *args, **kw) -> subprocess.CompletedProcess:
    """See gitutil.git_trusted: main checkout only, never `-C <worktree>`."""
    import gitutil
    return gitutil.git_trusted(repo, *args, **kw)


def _snapshot_tree(repo: Path, ref: str, dest: Path) -> Path:
    """The reviewed commit as plain files, read blob by blob from the main
    repo's object store (ls-tree + cat-file: no attributes, no filters, no
    worktree config). Only regular files are written, by us; symlinks and
    submodules are dropped, so nothing the unsandboxed script reads can
    point outside it."""
    r = _git_trusted(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}",
                     capture_output=True, text=True)
    if r.returncode != 0:
        raise WorkerError(f"could not snapshot {ref!r} for gate_services: {r.stderr.strip()[:300]}")
    sha = r.stdout.strip()
    r = _git_trusted(repo, "ls-tree", "-r", "-z", "--full-tree", sha, capture_output=True)
    if r.returncode != 0:
        raise WorkerError(f"could not list {sha} for gate_services: "
                          f"{r.stderr.decode(errors='replace').strip()[:300]}")
    entries = []
    for rec in r.stdout.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, kind, obj = meta.decode().split()
        rel = Path(path.decode("utf-8", errors="surrogateescape"))
        if kind != "blob" or mode not in ("100644", "100755"):
            continue  # symlink (120000), submodule (160000)
        if rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts:
            continue
        entries.append((obj, mode, rel))
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    batch = "".join(f"{obj}\n" for obj, _, _ in entries).encode()
    r = _git_trusted(repo, "cat-file", "--batch", input=batch, capture_output=True)
    if r.returncode != 0:
        raise WorkerError(f"could not read {sha}'s blobs for gate_services")
    buf, pos = r.stdout, 0
    for obj, mode, rel in entries:
        nl = buf.index(b"\n", pos)
        header = buf[pos:nl].split()
        if header[0].decode() != obj or header[1] != b"blob":
            raise WorkerError(f"unexpected cat-file output for {obj} while snapshotting {sha}")
        size = int(header[2])
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(buf[nl + 1:nl + 1 + size])
        if mode == "100755":
            target.chmod(0o755)
        pos = nl + 1 + size + 1  # content, then its trailing newline
    return dest


def _trap_signals(handle: dict) -> None:
    """A launcher killed outright (tmux pane closed) would skip every
    `finally` and leave the services running: turn SIGTERM/SIGHUP into
    SystemExit while services are up. Main thread only (Python's rule)."""
    if threading.current_thread() is not threading.main_thread():
        return
    def _exit(signum, _frame):
        raise SystemExit(128 + signum)
    handle["prev_signals"] = {sig: signal.signal(sig, _exit)
                              for sig in (signal.SIGTERM, signal.SIGHUP)}


def _restore_signals(handle: dict) -> None:
    for sig, prev in (handle.pop("prev_signals", None) or {}).items():
        signal.signal(sig, prev)


def start_gate_services(repo: Path, company_root: Path, role: str, actor: str,
                        project: str, task_id: str | None, ref: str,
                        verify_id: str) -> dict | None:
    """Bring up the project's gate_services for a gate role. Returns a handle
    for stop_gate_services (None: nothing to do — not a gate role, or none
    declared). Raises WorkerError, after tearing down whatever it started, if
    any `up` fails or its declared env vars can't be parsed: a gate that would
    only report UNVERIFIED is never launched."""
    if role not in GATE_VERDICT_EVENTS:
        return None  # implementers are untouched
    services = load_gate_services(company_root)
    if not services:
        return None
    # Denied to every sandboxed worker (sandbox_settings, guard_secrets).
    secret_dir = company_root / "secrets" / "gate_services"
    secret_dir.mkdir(parents=True, exist_ok=True)
    log_path = secret_dir / f"{_service_id(actor)}.log"
    snapshot = company_root / "state" / "gate-services" / verify_id
    handle = {"repo": repo, "company_root": company_root, "actor": actor,
              "project": project, "task": task_id, "env": None, "snapshot": snapshot,
              "log": log_path, "started": [], "inject": {}, "verify_id": verify_id}
    log = EventLog(company_root)
    _trap_signals(handle)
    try:
        base_env = dict(os.environ)
        base_env.update({"COMPANY_GATE_WORKTREE": str(_snapshot_tree(repo, ref, snapshot)),
                         "VERIFY_ID": verify_id})
        handle["env"] = base_env
        for svc in services:
            handle["started"].append(svc)  # down runs even for a half-started up
            code, output = _run_service_cmd(svc["up"], repo, base_env, svc["timeout_s"], log_path)
            problem = None
            if code != 0:
                problem = (f"timed out after {svc['timeout_s']}s" if code is None
                           else f"exited {code}")
            else:
                for var, rx in svc["env_from_output"].items():
                    # FIRST match wins: the script may echo output from the
                    # branch under review (its migrations) after its own
                    # line, and that must not be able to pick the gate's DB.
                    m = rx.search(output)
                    if not m:
                        problem = f"printed no value for {var} (/{rx.pattern}/)"
                        break
                    handle["inject"][var] = m.group(1)
            if problem:
                log.append(make_event(
                    event="GATE_SERVICES_UP", actor=actor, project=project,
                    data={"ok": False, "task": task_id, "role": role, "verify_id": verify_id,
                          "up": svc["up"], "exit_code": code, "error": problem,
                          "log": str(log_path)}))
                raise WorkerError(
                    f"gate_services `up` ({svc['up']}) {problem}, so the {role} gate was not "
                    f"launched (it could only report UNVERIFIED). Output: {log_path}")
        log.append(make_event(
            event="GATE_SERVICES_UP", actor=actor, project=project,
            data={"ok": True, "task": task_id, "role": role, "verify_id": verify_id,
                  "services": [s["up"] for s in services],
                  # names only: values (database URLs) can carry credentials
                  "env_vars": sorted(handle["inject"]), "log": str(log_path)}))
    except BaseException:
        stop_gate_services(handle)  # whatever went wrong, nothing is left running
        raise
    return handle


def _services_note(handle: dict | None) -> str:
    """Tell the gate what it was given. Without this a gate sees Docker
    denied by its sandbox and reports UNVERIFIED without ever looking for
    the URL in its env (finos m5-phase1, 2026-11-19: the single-task run
    only worked because the PM happened to say so in a handoff)."""
    if not handle or not handle["inject"]:
        return ""
    names = ", ".join(sorted(handle["inject"]))
    return ("\n\nGATE SERVICES (started for you by company-os, outside your sandbox)\n"
            f"These are set in your environment, pointing at services already running "
            f"against this review's commit: {names}. Use them for the database-backed "
            f"checks. Do not start or stop services yourself (Docker is denied to you "
            f"by design); company-os tears them down after you exit.\n")


def stop_gate_services(handle: dict | None) -> None:
    """Run every started service's `down`, newest first. Never raises: it runs
    from a `finally`, and must not mask the gate's own result — a failed
    teardown is recorded in GATE_SERVICES_DOWN instead."""
    if not handle:
        return
    gate = handle.pop("proc", None)
    if gate is not None and gate.poll() is None:
        # Only on an abnormal exit (the launcher itself was signalled): a
        # gate left running against a torn-down DB would report UNVERIFIED.
        gate.terminate()
    if not handle["started"]:
        _restore_signals(handle)
        shutil.rmtree(handle["snapshot"], ignore_errors=True)
        return
    # A second SIGTERM mid-teardown must not abort the `down` itself.
    for sig in handle.get("prev_signals") or {}:
        signal.signal(sig, signal.SIG_IGN)
    results = []
    try:
        for svc in reversed(handle["started"]):
            if not svc.get("down"):
                continue
            try:
                code, _ = _run_service_cmd(svc["down"], handle["repo"], handle["env"],
                                           svc["timeout_s"], handle["log"])
            except Exception as exc:  # noqa: BLE001 — recorded, never raised
                code = f"error: {exc}"
            results.append({"down": svc["down"], "exit_code": code})
    finally:
        handle["started"] = []
        _restore_signals(handle)
        shutil.rmtree(handle["snapshot"], ignore_errors=True)
    try:
        EventLog(handle["company_root"]).append(make_event(
            event="GATE_SERVICES_DOWN", actor=handle["actor"], project=handle["project"],
            # None, not True, when no service declared a `down`: nothing ran.
            data={"task": handle["task"],
                  "ok": all(r["exit_code"] == 0 for r in results) if results else None,
                  "verify_id": handle["verify_id"], "results": results,
                  "log": str(handle["log"])}))
    except Exception:  # noqa: BLE001
        pass


READONLY_TOOLS = "Read,Grep,Glob,Bash"


def role_tools(role: str) -> str:
    """The role's tool allowlist (Claude tool names, the vocabulary
    agents/*.md and ROLE_TOOLS use) — passed to Claude as --allowedTools and
    to every other harness's shim as $COMPANY_ALLOWED_TOOLS."""
    return ROLE_TOOLS.get(role, READONLY_TOOLS)


def build_command(task: dict, role: str, model: str | None = None,
                   effort: str | None = None, skip_permissions: bool = False,
                   harness_spec: dict | None = None, company_root: Path | None = None,
                   sandbox: dict | None = None,
                   plugin_root: Path | None = None) -> list[str]:
    """Fill the role's configured harness command template (config/harness.yaml).

    Model/effort come from staffing.yaml's tier policy (D11), not a default —
    switching either mid-task busts the prompt cache and re-prefills the
    whole conversation at full price, so this is set once at launch and never
    changed by a running worker. skip_permissions exists only for ESC-009
    (2026-10-17: Claude Code's own sensitive-file prompt blocks headless
    writes under .company/worktrees/<TASK>/ even with --permission-mode
    acceptEdits) — the ownership hook and protect_branches.py still fully
    constrain what a worker can touch; this only removes Claude Code's own
    extra prompt on top of them, and a harness without that flag configured
    just ignores the request.
    """
    spec = harness_spec or harness.resolve(harness.load_config(company_root or PLUGIN_ROOT), role)
    return harness.build_command(
        spec, role=role, plugin_root=plugin_root or PLUGIN_ROOT,
        allowed_tools=role_tools(role),
        schema=RESULT_SCHEMA, model=model, effort=effort,
        skip_permissions=skip_permissions, settings=sandbox,
    )


CLAIM_STALE_AFTER_S = 7200  # comfortably above any real launch timeout — a
# claim older than this without being released means its owning process died
# without ever reaching launch()'s `finally` (a hard kill), not that it lost
# a fair race to a concurrent competitor.


def claim_task(company_root: Path, task_id: str, actor: str) -> bool:
    """Atomically claim a task before launching, closing the race
    `live_worker_on` alone cannot.

    KNOWN_ISSUES #2: two `launch()` calls issued close together both read the
    filesystem (via live_worker_on) before either had written its own pid/
    started_task marker, so both observed "no live worker" and both
    proceeded — TASK-202 was implemented four times concurrently, 26.5% of a
    project's total tokens for a task whose merged diff was 101 lines. A
    check-then-act read is not a lock; `os.open(..., O_CREAT | O_EXCL)` is —
    the OS guarantees only one caller ever succeeds at creating the same path.

    First draft of this fix reclaimed a contested claim whenever
    live_worker_on found nothing live yet — which is exactly the state BOTH
    racing callers see while either is still mid-launch (neither has written
    its pid file), so the loser would immediately steal the winner's claim
    and reproduce the original bug. Age is the signal that's actually safe:
    a fresh claim might belong to a genuine concurrent competitor and must
    never be stolen; only a claim old enough that no real launch could still
    be legitimately holding it gets reclaimed.
    """
    live = live_worker_on(company_root, task_id)
    if live and live != actor:
        return False  # a fully-running worker (its own claim already released)

    claims = Path(company_root) / "state" / "claims"
    claims.mkdir(parents=True, exist_ok=True)
    claim_path = claims / f"{task_id}.claim"

    try:
        fd = os.open(str(claim_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, actor.encode())
        os.close(fd)
        return True
    except FileExistsError:
        pass

    holder = claim_path.read_text(encoding="utf-8").strip()
    if holder == actor:
        return True  # the same worker resuming its own claim, not a collision

    age = time.time() - claim_path.stat().st_mtime
    if age < CLAIM_STALE_AFTER_S:
        return False  # could be a genuine concurrent competitor — never steal it
    claim_path.write_text(actor, encoding="utf-8")  # leaked by a hard-killed process
    return True


def release_claim(company_root: Path, task_id: str) -> None:
    claim_path = Path(company_root) / "state" / "claims" / f"{task_id}.claim"
    claim_path.unlink(missing_ok=True)


def live_worker_on(company_root: Path, task_id: str) -> str | None:
    """Another worker already in this task's worktree, if any.

    Two workers in one worktree overwrite each other's edits and produce a diff
    neither of them intended. Detached launches make this easy to do by accident,
    so it is checked rather than trusted.
    """
    import json as _json
    workers = Path(company_root) / "state" / "workers"
    if not workers.is_dir():
        return None
    for pidfile in sorted(workers.glob("*/pid")):
        try:
            pid = int(pidfile.read_text().strip())
        except (ValueError, OSError):
            continue
        # slots._alive, not a bare os.kill(pid, 0): a zombie passes kill(0)
        # but is doing no work, and worktrees.cleanup must not treat a dead
        # worker's unreaped corpse as an owner forever.
        import slots
        if not slots._alive(pid):
            continue
        started = pidfile.parent / "started_task"
        if started.exists() and started.read_text().strip() == task_id:
            return pidfile.parent.name
    return None


def launch(repo: Path, company_root: Path, task: dict, packet: str,
           role: str, actor: str, timeout: int = 1800,
           model_override: str | None = None, effort_override: str | None = None,
           override_reason: str | None = None, skip_permissions: bool = False,
           review_sha: str | None = None) -> dict:
    """Run one Tier-2 worker to completion. Returns a result record.

    For a gate role, `review_sha` is the branch SHA the packet's diff was
    taken at (cli reads it once, branch_sha); read here if not given.

    model_override/effort_override replace staffing.yaml's tier policy for
    this one launch only — never persisted, never changes the policy for any
    other task. Per D11, escalating above policy needs a recorded reason;
    override_reason is required whenever either override is set and is
    written into WORKER_STARTED so the escalation is visible in the event
    log, not a silent one-off.

    Also refuses to start at all if this exact task has an open, blocking
    escalation (donor review, 2026-10-19 — real incident: VIDEO-LAUNCH-01
    was relaunched three times against the same unresolved environment
    blocker, ESC-009, each relaunch paying to reproduce the same failure
    with no new information). override_reason lets a caller who has
    confirmed the blocker is actually clear proceed anyway without first
    formally resolving the escalation — same discipline as the model/effort
    override above, not a separate mechanism.
    """
    if (model_override or effort_override or skip_permissions) and not override_reason:
        raise WorkerError(
            "model/effort/skip-permissions override requires --why (the reason is "
            "recorded in WORKER_STARTED, per D11's escalation-needs-a-reason discipline)")
    import escalations
    blocker = escalations.blocking_escalation_for_task(
        gatesig.trusted_events(EventLog(company_root).read(), gatesig.load_key(company_root)), task["id"])
    if blocker and not override_reason:
        raise WorkerError(
            f"{blocker['id']} is an open, blocking escalation on {task['id']!r} "
            f"({blocker.get('need')!r}) — relaunching against the same unresolved "
            f"blocker just pays to reproduce the same failure. Resolve it first "
            f"(`company resolve {blocker['id']}`), or pass --why if you've confirmed "
            f"the blocker is actually clear and want to proceed without formally "
            f"resolving it yet."
        )
    harness_spec = _guarded_spec(company_root, role, project=task.get("project", ""),
                                 actor=actor, task=task["id"])
    if not claim_task(company_root, task["id"], actor):
        busy = live_worker_on(company_root, task["id"]) or "another worker"
        raise WorkerError(
            f"{busy} is already working in {task['id']}'s worktree. Two workers in "
            f"one worktree overwrite each other. Wait for it, or `company stop`."
        )
    services = None
    try:
        log = EventLog(company_root)
        wt, branch = ensure_worktree(repo, company_root, task)
        _check_project(harness_spec, wt)
        sandbox = sandbox_settings(company_root, wt, role)
        plugin_root = launch_plugin_root(repo)  # before WORKER_STARTED: a failed export never starts
        # Before WORKER_STARTED too: a failed `up` never starts the gate.
        services = start_gate_services(repo, company_root, role, actor, task.get("project", ""),
                                       task["id"], branch, _service_id(task["id"]))

        state = company_root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out_path, err_path = state / "stdout.json", state / "stderr.log"

        policy_cfg = staffing.load_config(company_root, "staffing.yaml")
        policy = dict(staffing.model_policy(policy_cfg, tier=2, gated=bool(task.get("gates")), role=role))
        if model_override:
            policy["model"] = model_override
        if effort_override:
            policy["effort"] = effort_override

        event_data = {"role": role, "tier": 2, "branch": branch, "worktree": str(wt),
                      "timeout_s": timeout, "model": policy.get("model"),
                      "effort": policy.get("effort"), "harness": harness_spec["_name"],
                      "guards": harness_spec["_guards"],
                      "provider": harness_spec["_provider"]["_name"]}
        if model_override or effort_override or skip_permissions:
            event_data["policy_override"] = {
                "reason": override_reason,
                "model_override": model_override, "effort_override": effort_override,
                "skip_permissions": skip_permissions,
            }
        gate_key = _gate_key(company_root, role)
        commits = {task["id"]: review_sha or branch_sha(repo, branch)} if gate_key else {}
        started_ev = log.append(make_event(
            event="WORKER_STARTED", actor=actor, project=task.get("project", ""),
            task=task["id"], data=event_data,
        ), finalize=gate_key and gatesig.sign_started(gate_key, [task["id"]], commits))

        # A harness without Claude Code's own `--agent` persona loader never
        # sees agents/<role>.md at all, so its body has to travel in the
        # packet instead — the default `claude` harness skips this (it would
        # otherwise load the same persona twice, once natively and once
        # inline).
        worker_input = packet + _services_note(services)
        if not harness_spec.get("native_agent_loading"):
            worker_input = harness.load_persona(plugin_root, role) + "\n\n---\n\n" + worker_input

        env = build_env(repo, company_root, task, actor, wt,
                        thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec,
                        allowed_tools=role_tools(role), plugin_root=plugin_root,
                        extra_env=services and services["inject"])

        started = time.monotonic()
        with open(out_path, "w") as out, open(err_path, "w") as err:
            proc = subprocess.Popen(
                build_command(task, role, model=policy.get("model"), effort=policy.get("effort"),
                              skip_permissions=skip_permissions, harness_spec=harness_spec,
                              sandbox=sandbox, plugin_root=plugin_root),
                cwd=str(wt),
                env=env,
                stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
            )
            (state / "pid").write_text(str(proc.pid))
            (state / "started_task").write_text(task["id"])
            if services:
                services["proc"] = proc
            # The pid + started_task markers above are now on disk, which is
            # what live_worker_on's ongoing liveness check relies on — the
            # claim's only job was covering the window before this point, so
            # it can be released now rather than held for the worker's whole
            # runtime (the `finally` below covers the failure paths too).
            release_claim(company_root, task["id"])
            try:
                # The packet is the worker's entire context. Closing stdin
                # matters: a process with an inherited open stdin blocks
                # forever waiting for EOF instead of running the prompt.
                proc.communicate(input=worker_input, timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                # SIGTERM, not SIGKILL: it aborts the turn cleanly, tears down
                # the child process tree, and still runs SessionEnd hooks
                # (exit 143).
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                timed_out = True

        # Before WORKER_EXITED: once the exit is visible a relaunch may start
        # its own `up` under the same VERIFY_ID, and our `down` must not kill
        # it. (The `finally` call is then a no-op safety net.)
        elapsed = round(time.monotonic() - started, 1)
        stop_gate_services(services)
        result = _read_result(out_path, harness_spec, proc.returncode)
        session_id = result.get("session_id")
        if session_id:
            (state / "session_id").write_text(session_id)

        log.append(make_event(
            event="WORKER_EXITED", actor=actor, project=task.get("project", ""),
            task=task["id"],
            data={"exit_code": proc.returncode, "timed_out": timed_out,
                  "elapsed_s": elapsed, "session_id": session_id,
                  "is_error": result.get("is_error"),
                  "terminal_reason": result.get("terminal_reason"),
                  # On a Claude subscription no dollars are charged for these
                  # runs; what is actually consumed is tokens against the
                  # plan's limits. `cost_usd` is the harness's own estimate
                  # (Claude Code's client-side API-price estimate; None for a
                  # harness that reports none, e.g. codex), so it is recorded
                  # as an estimate and never presented as a bill.
                  "cost_usd_estimate": result.get("cost_usd"),
                  "tokens": _usage(result),
                  # How many turns the run actually took — the normalizer
                  # task/turn cost attribution (company costs) needs so a
                  # long genuinely-thorough run and a short run that
                  # re-reads redundantly per turn don't look identical just
                  # because their raw cache_read totals happen to match.
                  # Harness-dependent: present for `claude` (the result JSON
                  # reports it directly), absent for a harness whose adapter
                  # doesn't populate it yet.
                  "num_turns": result.get("num_turns")},
        ))

        if timed_out:
            log.append(make_event(
                event="TASK_FAILED", actor=actor, project=task.get("project", ""),
                task=task["id"],
                data={"reason": f"wall-clock timeout after {timeout}s",
                      "worktree_preserved": str(wt)},
            ))
        elif role in GATE_VERDICT_EVENTS:
            record_verdicts(log, gate_key, role, actor, task.get("project", ""),
                            started_ev["seq"], [task], result, proc.returncode, out_path,
                            commits)

        return {
            "actor": actor, "task": task["id"], "role": role, "branch": branch,
            "worktree": str(wt), "exit_code": proc.returncode, "timed_out": timed_out,
            "elapsed_s": elapsed, "session_id": session_id,
            "is_error": result.get("is_error"),
            "structured_output": result.get("structured_output"),
            "stdout": str(out_path), "stderr": str(err_path),
        }
    finally:
        # Covers every early-exit path above (ensure_worktree raising, etc.)
        # that never reached the release call in the normal path.
        stop_gate_services(services)
        release_claim(company_root, task["id"])


def launch_group(repo: Path, company_root: Path, group_id: str, tasks: list[dict],
                 worktree: Path, packet: str, role: str, actor: str, project: str,
                 timeout: int = 1800, review_shas: dict[str, str] | None = None) -> dict:
    """Run one gate launch against a combined worktree covering several
    tasks (efficiency addendum v1, 2026-08-24 — grouped gating). Structurally
    `launch()`, minus per-task worktree creation (the caller already built
    the group's combined worktree via `gategroup.build_group_review`) and
    with the post-exit verdict check applied to EVERY task in the group, not
    one — a task that didn't get its own verdict event is GATE_NO_VERDICT,
    same as a solo gate, never silently covered by a sibling's review.
    """
    # Per-role claim (2026-09-09), matching gategroup's per-role worktree and
    # branch. Keyed on group_id alone, this claim re-serialized the three gate
    # roles even after their worktrees stopped colliding: the second role was
    # refused outright rather than running alongside the first. Review, qa and
    # security are independent read-only judgments of the same merge, so the
    # thing that must not run twice is one ROLE on one group, not the group.
    claim_id = f"gate-group-{group_id}-{role}"
    harness_spec = _guarded_spec(company_root, role, project=project, actor=actor)
    _check_project(harness_spec, worktree)
    if not claim_task(company_root, claim_id, actor):
        busy = live_worker_on(company_root, claim_id) or "another worker"
        raise WorkerError(
            f"{busy} is already running the {role} gate on group {group_id!r}. "
            f"Wait for it, or `company stop`."
        )
    services = None
    try:
        log = EventLog(company_root)
        state = company_root / "state" / "workers" / actor
        state.mkdir(parents=True, exist_ok=True)
        out_path, err_path = state / "stdout.json", state / "stderr.log"

        policy_cfg = staffing.load_config(company_root, "staffing.yaml")
        policy = staffing.model_policy(policy_cfg, tier=2, gated=True, role=role)
        task_ids = [t["id"] for t in tasks]
        sandbox = sandbox_settings(company_root, worktree, role)
        plugin_root = launch_plugin_root(repo)  # before WORKER_STARTED: a failed export never starts
        # Per role: the group's three gates run concurrently, so each needs
        # its own service instance or one gate's `down` kills another's DB.
        # The branch gategroup.build_group_review made for this role's review.
        services = start_gate_services(repo, company_root, role, actor, project, None,
                                       f"_gate-group-{group_id}-{role}",
                                       _service_id(f"gg-{group_id}-{role}"))

        gate_key = _gate_key(company_root, role)
        # Each member's own branch SHA — what the group branch merged
        # (cli passes the ones it built it from).
        commits = ({t["id"]: (review_shas or {}).get(t["id"]) or branch_sha(repo, t.get("branch"))
                    for t in tasks} if gate_key else {})
        started_ev = log.append(make_event(
            event="WORKER_STARTED", actor=actor, project=project,
            data={"role": role, "tier": 2, "gate_group": group_id, "tasks": task_ids,
                  "worktree": str(worktree), "timeout_s": timeout,
                  "model": policy.get("model"), "effort": policy.get("effort"),
                  "harness": harness_spec["_name"], "guards": harness_spec["_guards"],
                  "provider": harness_spec["_provider"]["_name"]},
        ), finalize=gate_key and gatesig.sign_started(gate_key, task_ids, commits))

        env = build_env(repo, company_root, {"id": "", "project": project}, actor,
                        worktree, thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec,
                        allowed_tools=role_tools(role), plugin_root=plugin_root,
                        extra_env=services and services["inject"])
        env.pop("COMPANY_TASK", None)  # no single task — the worker cites task ids itself

        worker_input = packet + _services_note(services)
        if not harness_spec.get("native_agent_loading"):
            worker_input = harness.load_persona(plugin_root, role) + "\n\n---\n\n" + worker_input

        started = time.monotonic()
        with open(out_path, "w") as out, open(err_path, "w") as err:
            proc = subprocess.Popen(
                build_command({"id": claim_id}, role, model=policy.get("model"),
                              effort=policy.get("effort"), harness_spec=harness_spec,
                              sandbox=sandbox, plugin_root=plugin_root),
                cwd=str(worktree), env=env,
                stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
            )
            (state / "pid").write_text(str(proc.pid))
            (state / "started_task").write_text(claim_id)
            if services:
                services["proc"] = proc
            release_claim(company_root, claim_id)
            try:
                proc.communicate(input=worker_input, timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                timed_out = True

        # Before WORKER_EXITED: once the exit is visible a relaunch may start
        # its own `up` under the same VERIFY_ID, and our `down` must not kill
        # it. (The `finally` call is then a no-op safety net.)
        elapsed = round(time.monotonic() - started, 1)
        stop_gate_services(services)
        result = _read_result(out_path, harness_spec, proc.returncode)
        session_id = result.get("session_id")
        if session_id:
            (state / "session_id").write_text(session_id)

        log.append(make_event(
            event="WORKER_EXITED", actor=actor, project=project,
            data={"gate_group": group_id, "tasks": task_ids,
                  "exit_code": proc.returncode, "timed_out": timed_out,
                  "elapsed_s": elapsed, "session_id": session_id,
                  "is_error": result.get("is_error"),
                  "terminal_reason": result.get("terminal_reason"),
                  "cost_usd_estimate": result.get("cost_usd"),
                  "tokens": _usage(result),
                  "num_turns": result.get("num_turns")},
        ))

        missing_verdict = []
        if role in GATE_VERDICT_EVENTS:
            missing_verdict = record_verdicts(
                log, gate_key, role, actor, project, started_ev["seq"], tasks, result,
                proc.returncode, out_path, commits, group_id=group_id)

        return {
            "actor": actor, "gate_group": group_id, "tasks": task_ids, "role": role,
            "worktree": str(worktree), "exit_code": proc.returncode, "timed_out": timed_out,
            "elapsed_s": elapsed, "session_id": session_id,
            "is_error": result.get("is_error"),
            "structured_output": result.get("structured_output"),
            "missing_verdict": missing_verdict,
            "stdout": str(out_path), "stderr": str(err_path),
        }
    finally:
        stop_gate_services(services)
        release_claim(company_root, claim_id)


def _usage(result: dict) -> dict:
    """Token consumption — the thing a subscription actually meters.

    Cache reads usually dwarf output tokens, because a non-bare worker re-reads
    its cached context every turn. That is the number to watch when runs start
    hitting plan limits, not the dollar estimate.
    """
    u = result.get("usage") or {}
    return {
        "output": u.get("output_tokens") or 0,
        "input": u.get("input_tokens") or 0,
        "cache_read": u.get("cache_read_input_tokens") or 0,
        "cache_creation": u.get("cache_creation_input_tokens") or 0,
    }


def _guarded_spec(company_root: Path, role: str, *, project: str = "", actor: str = "",
                  task: str | None = None) -> dict:
    """The role's harness, refused before anything is claimed, created, or
    logged if company-os's guards can't reach its worker (H3, harness.py's
    GUARD_MODES). Applies to advisors too: the secret-read guard protects a
    read-only role exactly as much as a writing one.

    Also the role's model provider (providers.py, M4), refused at the same
    point if the harness can't carry it, its key isn't set, or the project's
    data classification forbids it. That last one is a judgment call
    (reroute or reclassify), so it is escalated, never silently rerouted."""
    spec = harness.resolve(harness.load_config(company_root), role)
    try:
        spec["_guards"] = harness.require_guards(spec)
    except harness.HarnessError as exc:
        raise WorkerError(str(exc)) from None
    try:
        prov = providers.resolve(providers.load_config(company_root), role)
        providers.check_classification(prov, providers.project_classification(company_root))
        providers.worker_env(prov, spec)  # raises now, not mid-launch
    except providers.ProviderIneligible as exc:
        import escalations
        escalations.raise_escalation(
            company_root, project=project, actor=actor, kind="decision", task=task,
            project_wide=not task,  # a provider/classification mismatch is project config
            need=f"{role} is routed to a model provider this project's data "
                 f"classification forbids: reroute the role or reclassify the project",
            detail=str(exc))
        raise WorkerError(str(exc)) from None
    except providers.ProviderError as exc:
        raise WorkerError(str(exc)) from None
    spec["_provider"] = prov
    return spec


def _check_project(spec: dict, project_root: Path) -> None:
    """harness.check_workdir, as a WorkerError: checked against the tree the
    harness will actually run in, before WORKER_STARTED."""
    try:
        harness.check_workdir(spec, project_root)
    except harness.HarnessError as exc:
        raise WorkerError(str(exc)) from None


def _read_result(path: Path, harness_spec: dict, exit_code: int | None) -> dict:
    """The run's normalized result, via the harness's own output adapter.

    The raw stdout stays in stdout.json (backfill.py re-parses historical
    Claude runs from it); the normalized form is written beside it as
    result.json, so what the event log recorded is inspectable after the fact
    without knowing which harness produced it.

    A provider key is scrubbed from stdout.json and stderr.log first, in
    place, so nothing read from them afterwards (result.json, events, the
    launch result) can carry it — a CLI that echoes its credentials in an
    error message would otherwise write it into the evidence trail."""
    values = providers.secrets(harness_spec.get("_provider"))
    for f in (path, path.parent / "stderr.log") if values else ():
        try:
            f.write_text(providers.redact(f.read_text(encoding="utf-8"), values),
                         encoding="utf-8")
        except OSError:
            pass
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raw = ""
    result = harness.read_result(harness_spec, raw, exit_code)
    try:
        (path.parent / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass  # evidence convenience only; the event log already has the facts
    return result


def launch_readonly(repo: Path, company_root: Path, project: str, packet: str,
                    role: str, actor: str, timeout: int = 900) -> dict:
    """Run an advisory officer against the repo itself.

    No worktree and no branch: advisors read, they never write. They are also
    not bound to a task, so the ownership hook stays inert — their agent files
    disallow Write and Edit outright, and Bash runs in the OS sandbox.

    The cwd is an empty per-advisor directory inside the repo, not the repo
    root: the sandbox always grants writes to the launch cwd, so launching
    in the repo root would leave an advisor's Bash free to write anywhere in
    the checkout (and a denyWrite on the repo also overrides the
    SANDBOX_WRITABLE dirs it needs for `company advise-finding`/`escalate` —
    verified live). Still under the repo, so the hooks' cwd-based repo
    detection and CLAUDE.md discovery are unchanged; the packet names the
    repository path explicitly.
    """
    log = EventLog(company_root)
    state = company_root / "state" / "workers" / actor
    state.mkdir(parents=True, exist_ok=True)
    out_path, err_path = state / "stdout.json", state / "stderr.log"
    cwd = state / "cwd"
    cwd.mkdir(exist_ok=True)
    sandbox = sandbox_settings(company_root, cwd, role)

    policy_cfg = staffing.load_config(company_root, "staffing.yaml")
    policy = staffing.model_policy(policy_cfg, tier=1, gated=False, role=role)
    harness_spec = _guarded_spec(company_root, role, project=project, actor=actor)
    _check_project(harness_spec, repo)  # the cwd is inside the repo

    log.append(make_event(
        event="WORKER_STARTED", actor=actor, project=project,
        data={"role": role, "tier": 1, "readonly": True, "timeout_s": timeout,
              "model": policy.get("model"), "effort": policy.get("effort"),
              "harness": harness_spec["_name"], "guards": harness_spec["_guards"],
              "provider": harness_spec["_provider"]["_name"]}))

    env = build_env(repo, company_root, {"id": "", "project": project}, actor, repo,
                     thinking=bool(policy.get("thinking", True)), harness_spec=harness_spec,
                     allowed_tools=READONLY_TOOLS)
    env.pop("COMPANY_TASK", None)   # not task-scoped; nothing to own

    cmd = harness.build_command(
        harness_spec, role=role, plugin_root=PLUGIN_ROOT,
        allowed_tools=READONLY_TOOLS, schema=None,
        model=policy.get("model"), effort=policy.get("effort"), settings=sandbox,
    )

    worker_input = packet
    if not harness_spec.get("native_agent_loading"):
        worker_input = harness.load_persona(PLUGIN_ROOT, role) + "\n\n---\n\n" + packet

    started = time.monotonic()
    with open(out_path, "w") as out, open(err_path, "w") as err:
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                                stdout=out, stderr=err, text=True)
        (state / "pid").write_text(str(proc.pid))
        try:
            proc.communicate(input=worker_input, timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            timed_out = True

    elapsed = round(time.monotonic() - started, 1)
    result = _read_result(out_path, harness_spec, proc.returncode)
    log.append(make_event(
        event="WORKER_EXITED", actor=actor, project=project,
        data={"exit_code": proc.returncode, "timed_out": timed_out,
              "elapsed_s": elapsed, "readonly": True,
              "session_id": result.get("session_id"),
              "cost_usd_estimate": result.get("cost_usd"),
              "tokens": _usage(result),
              "num_turns": result.get("num_turns")}))

    return {"actor": actor, "role": role, "exit_code": proc.returncode,
            "timed_out": timed_out, "elapsed_s": elapsed,
            "stdout": str(out_path), "stderr": str(err_path)}


def stop_all(company_root: Path, project: str | None = None) -> list[dict]:
    """`company stop` — halt every worker, preserve every worktree."""
    stopped = []
    workers = company_root / "state" / "workers"
    if not workers.is_dir():
        return stopped
    for pidfile in sorted(workers.glob("*/pid")):
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            stopped.append({"actor": pidfile.parent.name, "pid": pid, "signal": "TERM"})
        except (ValueError, OSError, ProcessLookupError):
            continue
    return stopped


def pause_task(company_root: Path, task_id: str) -> dict | None:
    """`company pause <task>` — halt the one worker running `task_id`,
    leaving every other running worker untouched. The deliberate complement
    of `stop_all`'s "halt everything": useful now that several workers can
    run concurrently and stopping all of them to hold back one is real
    collateral damage (donor review, 2026-10-19 — paperclip distinguishes
    Stop/Pause/Cancel as separate actions; this is company-os's version,
    scoped to what's actually true here: SIGTERM and worktree preservation,
    same as `stop_all`, just aimed at one actor instead of every actor).

    Returns None if no live worker is running that task — same "nothing to
    do" signal `live_worker_on` already uses elsewhere, not an error.
    """
    workers = Path(company_root) / "state" / "workers"
    if not workers.is_dir():
        return None
    for pidfile in sorted(workers.glob("*/pid")):
        started = pidfile.parent / "started_task"
        if not started.exists() or started.read_text().strip() != task_id:
            continue
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            return {"actor": pidfile.parent.name, "pid": pid, "signal": "TERM", "task": task_id}
        except (ValueError, OSError, ProcessLookupError):
            return None
    return None
