# Predator Threat Assessment

> CANDIDATE: proposed on 2026-04-08, awaiting review

## Purpose

Know the strongest predators in the game so you can set safe HP
thresholds per account and body type. A harvest loop that ignores
predator threat is flying blind — you don't know how much HP your
kamis can safely lose before a kill becomes possible.

## Threat Model: Affinity Matters

Liquidation efficacy depends on **attacker's hand** vs **victim's body**:

| Attacker Hand | vs Scrap body | vs Insect body | vs Eerie body | vs Normal body |
|---|---|---|---|---|
| **Eerie** | STRONG (+0.5) | WEAK (-0.5) | neutral | special (+0.2) |
| **Scrap** | neutral | STRONG (+0.5) | WEAK (-0.5) | special (+0.2) |
| **Insect** | WEAK (-0.5) | neutral | STRONG (+0.5) | special (+0.2) |
| **Normal** | special (+0.2) | special (+0.2) | special (+0.2) | neutral |

**Per-account threat priority:**
- Account with Scrap bodies: fear **Eerie hand** predators most
- Account with Normal bodies: no single worst matchup, but all affinities
  get +0.2 special bonus — moderate universal threat

## How to Detect Predators

### Signals (from `get_kami_state_slim`)

A kami is a predator build if ANY of:
- `stats.violence.total` > 20 (high base violence from traits + Mochi)
- `bonuses.attack.threshold.shift` > 0 (invested in ATS skills: 122, 142, 162)
- `bonuses.attack.threshold.ratio` > 0 (invested in ATR skills: 121, 151)
- Skills in 1xx range (Predator tree) with > 15 total points

### Threat Tier (combine signals)

| Tier | Violence | ATK Threshold Shift | ATK Threshold Ratio | Cooldown Reduction |
|---|---|---|---|---|
| **S — Apex** | 30+ | > 0.20 | > 0.40 | > -50s |
| **A — Dangerous** | 25+ | > 0.10 | > 0.20 | any |
| **B — Capable** | 20+ | > 0 | > 0 | any |
| **C — Incidental** | 15-20 | 0 | 0 | 0 |

### Affinity (requires `get_kami_state` — full endpoint)

The slim endpoint does NOT include `traits.hand.affinity`. To determine
which body types a predator threatens, you must call the full
`get_kami_state(kami_id)` endpoint and check `traits.hand.affinity`.

## Data Pipeline

### Step 1: Bulk scan (daily)

```
get_all_kamis() → 17K+ kamis, basic data only (index, name, state)
Filter: state == "HARVESTING" or state == "RESTING"
```

Returns ~13K active kamis. Cached 24h — run once per session.

### Step 2: Sample for predator builds

Query `get_kami_state_slim(kami_id)` for a targeted subset:
- Named kamis (non-default name = invested player, more likely predator)
- Low-index kamis (older = higher level = more skill points)
- Any kami sharing a node with your harvesters

Filter by predator signals above. This step is API-intensive — budget
~50-100 queries per session, prioritizing kamis on your active nodes.

### Step 3: Full profile for confirmed predators

For kamis passing the predator filter, call `get_kami_state(kami_id)` to
get hand affinity. Record in threat database.

### Step 4: Threat-adjusted HP thresholds

Once you know the strongest predator with the right hand affinity for
your account's body type, calculate the kill threshold they'd impose:

```
threshold = (animosity * efficacy + shift) * victimMaxHP / precision
```

Where `efficacy` includes the attacker's hand vs victim's body bonus,
and `shift` includes the predator's ATK threshold shift + ratio bonuses.

Set your harvest stop-HP above this threshold + safety margin.

If no strong predator with the matching hand affinity exists, you can
harvest more aggressively (lower HP thresholds).

## Current Landscape (illustrative snapshot, 2026-04-08)

> This section shows what a threat scan looks like. Numbers are from
> a point-in-time scan and will be outdated — re-run the pipeline
> above for current data.

- **17,328 total kamis**: 3,588 HARVESTING, 10,133 RESTING, 1,882 DEAD
- **Killer ranking: empty** — liquidation is early-stage, few or no kills
- **Sampled predators found:**
  - Godblessu #46 — Vio 34, ATK shift 0.28/ratio 0.5, INSECT hand, Lvl 45 (S-tier)
  - Scrappy #362 — Vio 29, ATK shift 0.26/ratio 0.25, SCRAP hand, Lvl 34 (A-tier)
- **Neither has Eerie hand** — no confirmed S/A-tier threat to Scrap-body accounts yet
- Most sampled kamis are guardian/harvester builds (Violence 10-13)

> HEURISTIC: predator builds are rare (~25% of named kamis in sample).
> Most players optimize for harvesting. But one dedicated predator on
> your node is all it takes — scan nodes you farm, not the whole game.

## Scaling Limitations

- `get_all_kamis` returns basic data only — no stats, no affinity
- Per-kami queries needed for violence/skills (slim) and affinity (full)
- No bulk stats endpoint exists yet
- Long-term: local MUD sync will allow direct component queries for
  violence, affinity, and skill data across all kamis at once

## When to Re-Scan

- After leveling season (new skill points allocated = new predators)
- When deaths appear on killer ranking
- When entering a new high-tier node for the first time
- Weekly as baseline (game population shifts)
