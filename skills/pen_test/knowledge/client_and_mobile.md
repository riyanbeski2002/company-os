---
name: client-and-mobile
description: Owned methodology for client-side endpoint classes — browser storage and service workers/PWA, mobile app security (storage, exported components, deep links, IPC, WebView), and desktop/Electron issues. The recurring theme — client-side restrictions are never a security boundary; verify the backend independently.
---

# Client & Endpoint

The unifying rule for this whole area: **anything enforced only on the client is
not a security boundary.** Every finding here is either a local exposure or a
pointer to test the server independently (`api_and_protocols.md`,
`idor_and_authz.md`).

## Browser storage & service workers / PWA

- **Sensitive data in LocalStorage/SessionStorage/IndexedDB** — tokens, PII,
  keys. Readable by any XSS (and by anyone on a shared machine). A JWT in
  LocalStorage is exfiltrable by XSS in a way an `HttpOnly` cookie isn't.
- **Autofill / clipboard / cache leakage** of sensitive values.
- **Service workers** — cache poisoning of a privileged response, stale
  privileged content served offline, insecure offline storage of private data,
  overly broad SW scope, and SW update security. A malicious or buggy SW persists
  across sessions.

## Mobile apps

- **Insecure local storage** — tokens/secrets in plaintext prefs, SQLite,
  or files; check keychain/keystore use.
- **Hard-coded secrets** in the APK/IPA (decompile and grep) — API keys, signing
  material, backend URLs.
- **Exported components / IPC** (Android) — exported activities/services/
  providers/receivers callable by other apps; intent manipulation; content
  providers leaking data.
- **Deep links / custom URL schemes** — unauthenticated actions, or params that
  reach a sensitive sink, triggerable by another app or a web page.
- **WebView issues** — `javascriptInterface` exposed to remote content, unsafe
  `loadUrl`, file access, mixed content.
- **Weak certificate validation / no pinning** — enables MITM
  (`cloud_and_infra.md`); test with an intercepting proxy + your CA.
- **Backup exposure** (`allowBackup`), and rooted/jailbroken assumptions.
- **The key point** — API authorization must hold **independent of client
  restrictions**: replay the app's API calls with a proxy and test authz/IDOR
  server-side, ignoring what the app UI allows.

## Desktop / Electron / WebView

- **Node integration exposure** — `nodeIntegration: true` on a window that loads
  remote or user content = RCE from web content.
- **Context isolation off / unsafe preload** — the preload bridge exposing
  privileged APIs to the renderer without a narrow, validated surface.
- **Unsafe IPC** — renderer→main messages that reach `fs`/`child_process` with
  attacker-controlled args.
- **Remote content / unsafe navigation** — loading untrusted URLs, external
  protocol handlers, `will-navigate` not restricted.
- **Update-channel security** — unsigned/unverified auto-updates, HTTP update
  feeds; **code-signing** validation gaps.
- **Secrets in packaged resources** — the `app.asar` is trivially unpacked; grep
  it like any other bundle (`secrets_and_supply_chain.md`).

## Validation bar

A local finding needs the actual exposed value and where it lives (the storage
key, the decompiled string, the exported component + the call that reaches it).
For anything that "the client blocks", the real finding is on the server: show
the API call succeeding with the client removed from the loop — otherwise it's a
hardening note, not an exploit.
