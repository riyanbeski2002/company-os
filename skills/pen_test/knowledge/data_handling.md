---
name: data-handling
description: Owned methodology for file- and data-processing classes — file upload, path traversal / Zip Slip, CSV/spreadsheet formula injection, PDF and image processing attack surface, import/export authorization, plus input-normalization and ReDoS/parser-abuse issues. The "the server ingests a file or a weird string" surface.
---

# File & Data Processing

Any point where the server accepts a file or an oddly-encoded string and does
something with it. Manual/`_httpcore`; some overlap with `ssrf_and_injection.md`
(XXE in documents, SSRF in converters) and `modern_stack.md` (deserialization).

## File upload

- **Extension / MIME validation bypass** — double extension (`shell.php.jpg`),
  null byte, case (`.PhP`), content-type mismatch (declare `image/png`, send
  script), trailing dot/space. Confirm where the file lands and whether it's
  served executable.
- **Polyglot files** — a valid image that's also a valid script/HTML; dangerous
  when the store is served from the app origin (stored XSS via SVG/HTML, or
  execution).
- **SVG active content** — SVG allows `<script>`; an uploaded SVG served inline
  is stored XSS. Also XML → XXE inside SVG/Office docs.
- **Filename / path injection** — `../` in the filename to write outside the
  upload dir (see path traversal); overwrite attacks on a predictable path.
- **Server-side processing** — the upload is resized/converted/scanned; that
  parser is the real attack surface (image/PDF sections below).
- **Public storage exposure** — the uploaded object is world-readable or
  predictably keyed (see `cloud_and_infra.md` / `multitenancy_and_baas.md`).

## Path traversal / LFI / Zip Slip

- **Path traversal** — `../../etc/passwd`, encoded (`%2e%2e%2f`), double-encoded
  (`%252e`), unicode/overlong, in any file/path parameter, download endpoint, or
  template/include path. Named-CVE variants (Apache 2.4.49/50) are in
  `cve_playbook.md`.
- **Zip Slip / archive traversal** — an uploaded archive with entries like
  `../../app/config.py`; extraction writes outside the target dir. Test if the
  app unzips user archives without canonicalizing entry paths.
- **Symlink escape** — an archive/file that symlinks out of the sandbox.

## CSV / spreadsheet formula injection

Exported data (or imported-then-exported) where a cell begins with `=`, `+`,
`-`, `@`, or tab/CR — opened in Excel/Sheets it executes (`=cmd|'/c calc'!A1`,
data-exfil via `=HYPERLINK`/`WEBSERVICE`). Test by submitting a formula in any
field that later appears in a CSV/XLSX export. Import side: unsafe parsing,
formula/DDE, and import authorization (importing into another tenant).

## PDF / document processing

Converters (HTML→PDF like wkhtmltopdf/headless Chrome, DOCX/XLSX processors) are
a rich surface: **SSRF / remote resource fetch** (an `<img>`/`<link>`/`@import`
in HTML-to-PDF pulls internal URLs — see `ssrf_and_injection.md`), embedded
active content, **XXE** in Office/ODF XML, metadata leakage, and temp-file
exposure. Feed a document that references a URL you control and watch for the
callback.

## Image / media processing

Unsafe parsers (ImageMagick "ImageTragick"-style, ffmpeg), **remote URL fetch**
by the processor (SSRF), metadata (EXIF/GPS) leakage or injection, and
decompression/resource exhaustion (pixel-flood, "image bomb"). Confirm with a
benign OOB callback or a controlled resource-use proof, not a destructive bomb.

## Input normalization & encoding

Double encoding, unicode homoglyph/normalization (a check on the raw string that
the sink normalizes into something dangerous — NFKC turning a lookalike into `<`
or `/`), null-byte handling, path/case normalization mismatches, alternate
encoding interpretation. These are *bypass amplifiers* — test them when a filter
blocks a straightforward payload, to see if the validator and the sink disagree
on what the input is.

## ReDoS / parser abuse

Catastrophic backtracking in a user-reachable regex (nested quantifiers like
`(a+)+$`); a crafted input that hangs a worker. Also parser differentials (two
parsers reading the same bytes differently — the root of smuggling, HPP, and some
normalization bugs). Prove ReDoS with a measured single-request latency spike, not
a flood — availability rules in `api_and_protocols.md` apply.

## Validation bar

The effect reproduced: a file served/executed where it shouldn't be, a file read
or written outside the sandbox (actual contents / actual out-of-path write), a
converter's OOB callback, a formula that executes on open, or a measured
processing-time/latency spike for ReDoS — not "the upload was accepted."
