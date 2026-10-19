# Isolated review environment (doc/UNTRUSTED-REVIEW.md). Builds a minimal
# image that can clone an UNTRUSTED target (an external PR, a dependency
# fork, anything not already trusted enough to touch the host) and run a
# read-only review role against it with no host filesystem, SSH, or git
# credential access — only what this image and the compose file's own
# volumes provide.
#
# Modeled on paperclip's docker/untrusted-review/ (github.com/paperclipai/
# paperclip, MIT) — read as a reference for the shape of the problem, not
# copied; company-os's own harness/CLI differ enough that the actual
# Dockerfile, entrypoint, and compose profile here are written fresh.
FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages pyyaml

# Both harnesses company-os ships today, so either can review inside this
# image regardless of which one is configured as the default on the host —
# the container has its own isolated world, it doesn't inherit the host's
# harness choice.
RUN npm install -g @anthropic-ai/claude-code @openai/codex

# Just the role definitions (so the reviewer persona inside the container is
# the real agents/<role>.md, not a paraphrase) — not the host's live
# checkout, not external/ (gitignored, main-checkout-only, and irrelevant to
# a one-off isolated review). Deliberately NOT importing tools/company/
# harness.py here: that module pulls in staffing.py/pathrules.py for
# load_config/resolve, machinery this container has no use for — the
# frontmatter-stripping it needs is five lines, inlined in the entrypoint
# below, rather than dragging in company-os's whole module graph.
RUN useradd -m -s /bin/bash reviewer
COPY --chown=reviewer:reviewer agents /opt/company-os/agents
COPY --chown=reviewer:reviewer docker/untrusted-review/entrypoint.sh /usr/local/bin/review-entrypoint
RUN chmod +x /usr/local/bin/review-entrypoint \
    && mkdir -p /work/target /work/output && chown -R reviewer:reviewer /work

USER reviewer
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/review-entrypoint"]
