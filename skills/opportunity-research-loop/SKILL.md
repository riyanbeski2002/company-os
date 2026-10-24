---
name: opportunity-research-loop
description: Use when the goal is to find, research, validate, and plan business/product opportunities from market signals — not to build a specific named app. A five-role loop (Scout → Researcher → Validator → Strategist → Builder) with a strict honesty rule - every claim cites a source or is labelled an assumption, and finding an opportunity is never confused with making money. Triggers on - find opportunities, what should I build, market scan, validate demand, is there demand for, business idea research.
---

# Opportunity Research Loop

A system that **finds and evaluates** opportunities — it does not promise income
and must never fake data. Used right, it is a research assistant that runs the
discovery process faster and more honestly. Finding an opportunity is not the
same as making money; the building and the work are still the user's.

Original write-up of the methodology from "Build Your AI Money OS" (by
@seb.ai). No code vendored.

## The honesty rule (this is the whole point)

- Every trend, demand signal, or number **cites where it came from**. No source
  → it is labelled an **ASSUMPTION**, visibly, not stated as fact.
- A researched fact and an AI guess are always marked differently.
- "No real demand found" is a **valid and valuable** answer. The Validator
  exists to produce that answer honestly, not to cheerlead.

## The five roles (run as a file relay; each writes to the opportunity's file)

1. **Scout — the eyes.** Reads the user's interests/budget, searches for
   emerging trends, growing problems, new tools, underserved markets. Outputs
   10–15 candidates, each with a source link; anything unsourced is marked
   ASSUMPTION. Never invents trends or demand.
2. **Researcher — investigates.** For each shortlisted idea: the real problem,
   who has it, who already solves it (competitors), how big it might be. Cites
   every source; separates EVIDENCE (sourced) from MY READ (assumption). Never
   fabricates stats or revenue figures.
3. **Validator — the skeptic.** Looks for REAL demand evidence: people
   complaining, searching, paying, asking for solutions (forums, reviews, search
   trends). Rates demand Strong / Some / Weak / None, with sources. A great-
   sounding idea with no real demand scores low.
4. **Strategist — the plan.** For a validated opportunity: the offer, the target
   customer, how it makes money, rough cost/effort to start, the biggest risk.
   Honest about difficulty; no hype, no guaranteed-income claims.
5. **Builder — the steps.** Turns the plan into an ordered checklist a beginner
   could start this week: the first 5–10 concrete steps, the cheapest/fastest
   way to test it, and how to know if it's working.

## Scoring

Each opportunity is scored 1–10 on five factors, honestly (high scores must be
earned by evidence): **Opportunity** (how big/real the upside), **Difficulty**
(higher = easier to build), **Competition** (higher = more open), **Startup
cost** (higher = cheaper), **Monetization** (how clear the path to revenue).
Average the five. **Demand evidence from the Validator is the tiebreaker.**

## Memory

Persist interests (so results fit the user), discoveries (so nothing repeats),
and results (what was tried and how it went). End a session by saving findings.
Next scan starts from everything learned.

## When NOT to use this

- The user already knows what they want built — route to the build/trading/video
  playbook instead; this loop is for the "what is worth building?" question.
- Any output that would state a projected income as fact — that violates the
  honesty rule.
