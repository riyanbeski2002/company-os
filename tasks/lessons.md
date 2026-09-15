# Lessons

## Cache-read tokens are not the usage-limit driver — don't blame them
**What happened:** Built a worker-ledger dashboard showing 96% of a day's tokens
were `cache_read` (103.9M of 108.4M) and told Riyan this was "the strongest
evidence yet" that per-task gate launches were burning his session limit,
because each cold-start worker re-pays a full context-reload tax.
**Why it was wrong:** researched it — on current models, `cache_read_input_tokens`
do not count toward Anthropic's rate/session limits at all; only
`input_tokens` + `cache_creation_input_tokens` do, and cache reads are billed
at ~10% of base input rate. A huge cache-read number is prompt caching
*working*, not a cost problem.
**What actually drives limit usage:** launch *count* (each fresh worker pays
`cache_creation` at 1.25x rate to write its context in, and that DOES count
toward the limit) and `output` tokens from long exploratory sessions — not
how much of the prompt was served from cache.
**How to apply:** when diagnosing a usage-limit spike, look at
`cache_creation + input + output` per hour, not raw token totals or the
cache-read share. Fewer, better-batched worker launches (gate-at-PR, not
per-task) reduces the number of `cache_creation` cold-starts directly — that's
the real lever, not "reduce cache reads."
