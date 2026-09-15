"""Glob matching for file ownership (D5).

`fnmatch` treats `**` no differently from `*`, which would silently widen
every `services/auth/**` rule into `services/*`. Ownership is enforcement, not
a suggestion, so the matcher is written out rather than borrowed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path, PurePosixPath


@lru_cache(maxsize=512)
def _translate(pattern: str, literal_brackets: bool = False) -> re.Pattern[str]:
    """Translate a git-style glob into a regex.

    `**`  matches across separators (any number of path segments)
    `*`   matches within one segment
    `?`   matches one character within a segment
    `[...]` matches one character from the class, within one segment
            (`[!...]`/`[^...]` negates; a literal `]` may lead the class)

    With `literal_brackets=True`, `[` and `]` are matched as ordinary
    characters instead of opening a class. See `matches` for why both
    readings are tried.
    """
    i, out = 0, ["^"]
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[" and not literal_brackets:
            end = pattern.find("]", i + 2)  # +2: a leading `]` in the class is literal
            if end == -1:
                out.append(re.escape(c))
                i += 1
                continue
            body = pattern[i + 1:end]
            negate = body[:1] in ("!", "^")
            chars = body[1:] if negate else body
            # Only `\` needs escaping inside a class; `-` stays live so
            # ranges like `[a-z]` keep working, matching glob convention.
            escaped = chars.replace("\\", "\\\\")
            cls = f"[^{escaped}]" if negate else f"[{escaped}]"
            # A lookahead, not a `/` baked into the class, blocks `/` even
            # when a range implies it (e.g. `[.-0]` spans the `/` byte).
            out.append(f"(?:(?!/){cls})")
            i = end + 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return re.compile("".join(out))


def matches(path: str, pattern: str) -> bool:
    """Does `path` match `pattern`?

    A `[...]` group is genuinely ambiguous: it is glob character-class syntax,
    but it is also a literal directory name in every framework that encodes
    dynamic route params in the filesystem (Next.js `app/role/[sheetId]/`,
    SvelteKit, Nuxt). Reading it only as a class made such a path fail to match
    even *itself*, so those files could not be owned by any glob at all — which
    in practice pushed workers into bypassing the ownership guard rather than
    losing access to their own route files.

    Both readings are therefore accepted. This can only ever add a match, never
    remove one, and only for patterns that contain brackets in the first place;
    a false positive needs a path that literally contains the bracket text.
    That asymmetry is deliberate: an unownable real file breaks the guard,
    while an over-broad bracket pattern is a rounding error.
    """
    rel = str(PurePosixPath(path))
    for literal in (False, True):
        if _translate(pattern, literal).match(rel):
            return True
        # `services/auth/**` should own `services/auth` itself, not just its children.
        if pattern.endswith("/**") and _translate(pattern[:-3], literal).match(rel):
            return True
    return False


def matches_any(path: str, patterns) -> str | None:
    for p in patterns or ():
        if matches(path, p):
            return p
    return None


def relative_to_repo(target: str, repo_root: str) -> str | None:
    """Return the repo-relative POSIX path, or None if target escapes the repo."""
    try:
        t = Path(target).resolve()
        r = Path(repo_root).resolve()
        return str(t.relative_to(r).as_posix())
    except (ValueError, OSError):
        return None


def check(path_rel: str, owned, forbidden) -> tuple[bool, str]:
    """Decide whether a write to `path_rel` is permitted.

    Forbidden wins over owned: an explicit exclusion is never overridden by a
    broad ownership pattern.
    """
    hit = matches_any(path_rel, forbidden)
    if hit:
        return False, f"{path_rel} matches forbidden glob {hit!r}"
    if not owned:
        return False, f"{path_rel} is outside this task's ownership (no owned globs declared)"
    hit = matches_any(path_rel, owned)
    if hit:
        return True, f"{path_rel} is owned via {hit!r}"
    return False, (
        f"{path_rel} is outside this task's owned globs "
        f"({', '.join(repr(g) for g in owned)})"
    )
