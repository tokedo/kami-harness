# Strategies

Calibrated strategic wisdom learned through gameplay and human review.

Unlike `systems/` (game mechanics) or `memory/` (per-instance state),
strategies are **shared knowledge** committed to the repo. Any agent instance
benefits from reading them. They answer "what works and why" — proven decision
heuristics that emerged from actual play, not theoretical mechanics.

## How strategies get here

```
agent plays → logs decisions in memory/decisions.md
           → founder reviews decisions
           → corrections and proven patterns get promoted here
```

This is the **calibration loop**. The agent proposes, the founder validates,
and confirmed insights graduate from ephemeral decision logs into permanent
strategy files.

## Confidence markers

- `> CALIBRATED:` — tested and confirmed through human review. Include the
  confirmation date. The agent should treat these as strong priors.
- `> CANDIDATE:` — proposed by the agent, awaiting founder review. The agent
  may follow these but should note when it does, so the founder can validate.
- `> HEURISTIC:` (in `systems/` files) — untested mechanical intuition. Not
  the same as a candidate strategy.

## How to read strategies

On session start, read `strategies/INDEX.md` **before** making plans. Strategy
files inform plan creation and revision — they are the accumulated wisdom that
prevents the agent from repeating mistakes or missing known optimizations.

During execution, strategy files are reference material. If a decision point
matches a documented strategy, follow it unless the situation has clearly
changed.

## File structure

Each strategy file covers one topic. Format:

```markdown
# <Strategy topic>

## <Pattern name>

<When to apply — conditional, terse.>

<What to do — concrete decision rule.>

<Why it works — the game mechanic reasoning.>

<When NOT to apply — edge cases, exceptions.>

> CALIBRATED: confirmed by human review on <YYYY-MM-DD>
```

Keep them terse and conditional, same style as `systems/` files. No narrative.
