---
name: modern-stack
description: Owned methodology for vulnerability classes specific to modern web stacks — GraphQL, NoSQL injection, insecure deserialization, prototype pollution, and SSTI — that the classic SQLi/IDOR/JWT set doesn't cover.
---

# Modern-Stack Vulnerability Classes

The classic classes (SQLi, IDOR, JWT, SSRF) still dominate, but modern JS/API
stacks add their own. These are the ones the field engagements actually run into.

## GraphQL

Run `native/graphql_probe.py <endpoint>`. It checks the four GraphQL-specific
exposures:

- **Introspection on** → the whole schema dumps: every query, mutation, type,
  field. Often reveals admin-only mutations reachable by anyone.
- **Field suggestions** ("Did you mean …?") → schema leaks field-by-field even
  with introspection off.
- **Dangerous mutations** (`deleteUser`, `setRole`, `createAdmin`) → reachable
  without the UI showing them = broken function-level authz (BFLA). Confirm with
  a low-priv token, same discipline as `idor_and_authz.md`.
- **Batching / aliases** → many operations in one HTTP request bypass
  per-request rate limits (credential stuffing, OTP brute force).

Common endpoints if `/graphql` 404s: `/api/graphql`, `/v1/graphql`, `/query`, `/gql`.

## NoSQL injection (MongoDB et al.)

Where a SQL app takes `user=alice&pass=secret`, a Mongo-backed one may accept
operator objects. Test **auth bypass** first:

- JSON body: `{"user":"admin","pass":{"$ne":null}}` or `{"$gt":""}` — matches any password.
- Query/form: `user[$ne]=&pass[$ne]=` (PHP/Express array-parsing).
- `$regex`, `$where` (JS eval — can be blind-boolean or even RCE-ish), `$gt/$lt`
  for blind extraction.

Signal: a login/filter that succeeds or changes behavior with an operator where
a plain string failed. `sqli_probe.py`'s boolean-blind logic doesn't cover
operator injection — test these manually via `_httpcore` or curl with the
operator in the right location (`--location json` matters).

## Insecure deserialization

Look for serialized blobs in cookies/params/bodies: Java (`rO0AB…` base64,
`AC ED 00 05` magic), .NET (`AAEAAAD…`, ViewState), PHP (`O:8:"…":`),
Python pickle, Ruby Marshal, Node `node-serialize`. A gadget chain turns these
into RCE. Detection: identify the format and framework; confirm the sink
deserializes untrusted input (error on a corrupted blob is a strong tell).
Exploitation (ysoserial / ysoserial.net gadget chains) is high-impact and
high-blast-radius — only with explicit authorization for code execution.

## Prototype pollution (JS/Node)

Merging attacker JSON into an object without guarding `__proto__`/`constructor`/
`prototype` pollutes `Object.prototype`, changing app behavior globally.
- Test: send `{"__proto__":{"polluted":"yes"}}` (or `constructor[prototype][x]`
  in query params) to a merge/config endpoint; then check if an unrelated
  response/behavior now reflects the injected property.
- Impact ranges from DoS to privilege bypass to RCE (when a polluted property
  feeds a template/child_process sink). Client-side variants pollute the DOM/gadget.

## Server-Side Template Injection (SSTI)

Covered in `ssrf_and_injection.md` too; the modern-stack angle: template engines
in Node/Python web apps (Jinja2, Nunjucks, Handlebars, EJS, Pug, Twig, Freemarker).
- Detect: inject `${7*7}`, `{{7*7}}`, `<%= 7*7 %>`, `#{7*7}` into any field that
  ends up rendered; `49` in the output = template evaluation.
- Fingerprint the engine (each has distinct syntax/error behavior), then use the
  engine-specific RCE gadget. High impact — treat like deserialization on authz.

## Validation bar

Same as everywhere: GraphQL introspection is confirmed by the dumped schema; a
NoSQL/SSTI/prototype-pollution finding needs the actual bypass/evaluation/behavior
change reproduced, not a payload that merely didn't error. RCE-class findings
(deserialization, SSTI, pollution-to-RCE) require explicit code-execution
authorization before you weaponize past a benign proof (`7*7`, a DNS callback).
