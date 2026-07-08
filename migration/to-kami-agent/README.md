# Staging: content bound for `kami-agent`

This directory is **temporary**. It holds agent *policy* — strategy,
memory schema, decision procedures, operating-mode runners — that was
removed from `kami-harness` when the harness was refactored into a pure
environment interface for KamiBench (see the root
[`CHANGELOG.md`](../../CHANGELOG.md), release `v1.0.0`).

The guiding rule of that refactor: **mechanics stay, judgment leaves.**

- *Mechanics* (facts about the world: tool schemas, catalogs, system
  docs, timing tables, entity references) stayed in `kami-harness`.
- *Judgment* (advice: "should", "prefer", "best", decision procedures,
  playbooks, calibrated strategy) moved here.

Nothing was deleted. Everything here is staged verbatim so it can be
moved into the new `kami-agent` repo (the reference agent scaffold that
builds against this environment interface), after which this directory
will be deleted from `kami-harness` in a follow-up.

## Contents

| Path | Origin in `kami-harness` | What it is |
|---|---|---|
| `CLAUDE.md` | repo root | Playing-agent instructions: session protocol, per-tick decision priorities, hard rules, tool-usage policy. |
| `strategies/` | `strategies/` | Calibrated decision heuristics learned through gameplay (README, INDEX, predator-threat-assessment). |
| `systems-memory.md` | `systems/memory.md` | Agent memory schema + templates: account roster, snapshots, plan hierarchy, decision log, calibration loop, session lifecycle. |
| `decision-checklists.md` | `README.md` | The per-tick decision checklist and the strategy/memory "layer" prose, cut verbatim from the old README. |
| `operating-modes.md` | `SETUP.md` | Hybrid vs Fully-Autonomous operating modes, the cron runner narrative, and autonomous session lifecycle, cut verbatim from the old SETUP. |
| `session-prompt.md.example` | repo root | The autonomous-mode session prompt template. |
| `scripts/run-session.sh.example` | `scripts/` | The cron-triggered autonomous session runner. |

## For the `kami-agent` maintainer

These files describe how an agent *played* the game against this harness.
Re-home them as the reference agent's policy layer. The environment
interface they build against is the `kami-harness` MCP server, versioned
via `SCHEMA_VERSION` (see the harness `CHANGELOG.md`).
