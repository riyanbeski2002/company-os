---
name: trading-research-loop
description: Use when building or reviewing an AI-assisted trading/strategy-research system — research → code → backtest → paper-trade → post-mortem → memory. Enforces paper-trading-only by default, a CODE-level kill switch (never a prompt-level one), and the overfitting defenses that stop a "self-improving" loop from fooling itself. Triggers on - trading bot, trading agent, backtest, strategy research, quant loop, paper trading, stock/crypto strategy.
---

# Trading Research Loop

A trading research system is the loop every quant desk runs: **research → code
→ backtest → live → post-mortem → remember.** AI agents can run it fast. The
danger is that speed makes it easy to fool yourself, so most of this skill is
about *not* doing that. The goal is to run the research process faster and more
honestly — never to promise an edge. Most strategies, including AI-built ones,
lose money.

This is an original write-up of the methodology from "How to Build a
Self-Improving AI Trading Research Loop" (skool.com/raycfu). No code is
vendored; re-verify any specific API before use. **Not financial advice.**

## Hard rules — these are not negotiable, and they are gates, not suggestions

1. **Paper trading only by default.** Fake money, real market data (e.g. an
   Alpaca paper account). Real-money / live execution is a separate, explicitly
   approved decision — in company-os it is an **escalation to Riyan**, never a
   default, and `config/` holding live keys is a stop.
2. **The kill switch lives in CODE, never in a prompt.** A risk limit written
   into an agent's instructions is a suggestion an AI can reason past. A check
   that runs before every order cannot be talked around:

   ```python
   # risk.py — runs before EVERY order; if it returns False the order never
   # reaches the broker, no matter what the agent argues.
   def check_order(order, account, limits):
       if account["daily_loss_pct"] >= limits["max_daily_loss_pct"]:
           return False, "Daily loss limit hit."
       if account["drawdown_pct"]  >= limits["max_drawdown_pct"]:
           return False, "Max drawdown hit."
       if order["value"] > account["equity"] * limits["max_position_pct"]:
           return False, "Order exceeds position limit."
       if account["open_positions"] >= limits["max_open_positions"]:
           return False, "Too many open positions."
       return True, "OK"
   ```
   If an order ever reaches the broker without passing this first, fix that
   before anything else.
3. **Never fake data.** A researched fact and an AI assumption are labelled
   differently, always. "No edge found" is a valid, valuable result.

## The six steps

1. **Research** — several specialist agents (Price Analyst, Fundamentals
   Reader, Macro Watcher, and a Skeptic whose only job is to argue why each idea
   fails). Run them **independently** — each writes its own memo without seeing
   the others, or they anchor. Each proposes ≤3 testable ideas, each stating
   what result would prove it wrong. Every agent checks the ledger (step 6)
   first and does not re-propose a failed idea unless conditions clearly changed.
2. **Code** — one file per strategy, versioned, same shape every time: entry
   rules, exit rules, position sizing, risk limits. Unit-test that entries/exits
   fire exactly when they should. No backtest yet.
3. **Backtest like you're trying to kill it** — the most important step:
   - **Write the prediction first** (expected return, win rate, failure
     condition) and seal it so goalposts can't move.
   - **Lock away a test period** (most recent 20–30%). It is touched **once**,
     at the very end. Test-tweak-retest on it voids it.
   - **Walk-forward**: train on one window, test on the next, slide, repeat.
   - **Adjust for attempts**: track how many variations were tried and apply a
     **Deflated Sharpe Ratio**. 500 variations guarantees one looks great by luck.
   - **Breaker agent**: a separate agent runs it at 2× costs, across the worst
     historical periods, with delayed fills. Survives only perfect conditions →
     it doesn't survive.
   - Revisions are capped (3–5 per idea); each counts as an attempt and raises
     the bar. A strategy needing 40 rewrites to pass has told you the answer.
4. **Paper trade** — only strategies that passed step 3 incl. one clean run on
   the sealed period. Every order through `check_order` first. Log every
   decision to a journal (timestamp, strategy+version, market conditions,
   decision, reasoning).
5. **Post-mortem** — a Critic agent reads the journal weekly, compares paper
   results to backtest and to the written prediction, and is blunt about what
   is overfit and what to pause. Backtest-great-but-paper-bad = overfit, now
   known.
6. **Memory (the self-improving part)** — a SQLite **hypothesis ledger**: every
   idea ever tested, its market regime, variation count, backtest/sealed/paper
   results, status, and lessons. **Failed ideas are the most valuable rows.**
   Research agents read it before proposing; the Critic writes lessons back.
   This — not a strategy that rewrites itself until it looks good — is what makes
   the loop self-improving.

## The failure you are guarding against

A loop told "backtest failed → rewrite → retest until it passes" will always
eventually pass, by fitting the past by luck. That is overfitting, the number
one way automated research loses money. Steps 3 and 6 exist to make each attempt
cost something and to stop rediscovering the same failed idea.

## When NOT to use this

- A simple price alert or portfolio tracker with no strategy/execution — that's
  an app build, not a research loop.
- Anything that would move real money without an explicit, separate approval.
