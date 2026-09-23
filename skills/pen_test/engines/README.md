# engines/

Continuously-updated third-party engines live here but are **not** shipped in
this skill package — their whole value is a live feed, so a frozen copy would be
misleading. They are (re)created on first use by `scripts/update_engines.sh`:

- `sqlmap/` — cloned + `git pull`-refreshed by `update_engines.sh`.
- `nuclei` / `trivy` / `semgrep` — installed as binaries; their feeds/rules
  self-update.

Run `bash scripts/update_engines.sh` once per machine (and before any real
engagement) to populate this directory and refresh the feeds.
