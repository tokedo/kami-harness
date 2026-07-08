# Decision checklists & policy layers (cut verbatim from `README.md`)

These sections were removed from the `kami-harness` README during the
environment-interface refactor because they are agent *policy* (decision
procedures and the strategy/memory layer description), not world
mechanics. Preserved here verbatim for migration into `kami-agent`.

---

## Per-Tick Decision Checklist

On each agent decision cycle, evaluate in priority order:

1. **Death check**: if any Kami has HP = 0 and state = `DEAD`, decide whether
   to revive (costs 33 Onyx) or leave dead
2. **Harvest danger**: for each harvesting Kami, estimate current HP from
   strain. If HP < 30% of max, collect or stop immediately
3. **Cooldown gate**: if Kami is on cooldown, skip to next Kami or wait
4. **Collect vs stop**: if accrued bounty is substantial and HP is safe,
   collect (keeps harvesting). If HP is getting low or need to act, stop
5. **Scavenge claims**: if any node's scavenge bar has claimable tiers,
   claim them (then reveal droptable commits next tick)
6. **Droptable reveals**: if pending commit-reveal transactions exist,
   execute reveals
7. **Level up**: if any resting Kami has XP >= level cost, level up and
   spend skill point
8. **Quest progress**: check completable quests → complete → accept next
9. **Restart harvest**: if a Kami is resting and HP is healthy (>50% max),
   pick best available node and start harvesting
10. **Economy**: craft if profitable recipes available, trade if favorable
    orders exist, buy from NPC shops if needed

> When restarting harvest, node selection priority:
> affinity match > high-value droptable > low occupancy > low scav cost.
> See [systems/harvesting.md](systems/harvesting.md) for the full framework.

---

## Strategies (calibrated wisdom) — README system entry

Proven decision heuristics learned through gameplay and human review. Committed
to the repo — shared across agent instances. Read `strategies/INDEX.md` before
planning. Insights flow from the decision log through the calibration loop:
agent plays, founder reviews, confirmed patterns get promoted to `strategies/`.
See [strategies/README.md](strategies/README.md).

---

## Memory (persistence) — README system entry

Multi-account state — portfolio plans, per-account snapshots, decisions —
persisted in `memory/` (gitignored). A single mastermind agent controls 1–N
accounts. Reads the roster, perceives all accounts, then executes
portfolio-level plans that coordinate work across accounts.
See [systems/memory.md](systems/memory.md).
