# Liquidation (PvP)

How liquidation eligibility, kill threshold, recoil, and loot are computed.

## Kill Eligibility

An attacker can liquidate a victim when **all** of these are true:

1. Both Kamis are `HARVESTING` on the **same node**
2. Attacker owns the attacking Kami
3. Attacker's account is in the same room as the node
4. Attacker is not on cooldown
5. Attacker HP > 0 (not starving)
6. **Victim's HP < kill threshold**

## Kill Threshold

The threshold determines what HP level makes a Kami killable:

```
threshold = (animosity * efficacy + shift) * victimMaxHP / precision
```

If the combined value is negative, threshold = 0 (unkillable).

### Config Values (Read On-Chain)

These config arrays control all kill math. Read them at startup via
`component.value` using `keccak256("is.config", configName)`:

| Config Key | Indices Used | Controls |
|---|---|---|
| `KAMI_LIQ_ANIMOSITY` | `[2]` = ratio, `[3]` = precision exp | Base kill threshold from stat ratio |
| `KAMI_LIQ_THRESHOLD` | `[2]` = base efficacy | Affinity modifier on threshold |
| `KAMI_LIQ_KARMA` | `[2]` = ratio, `[3]` = precision exp | Recoil karma multiplier |
| `KAMI_LIQ_RECOIL` | `[0]` = nudge, `[1]` = nudge prec, `[6]` = boost, `[7]` = boost prec | Recoil damage calculation |
| `KAMI_LIQ_SALVAGE` | `[0]` = nudge, `[1]` = nudge prec, `[2]` = base ratio, `[3]` = ratio prec | Victim bounty retention |
| `KAMI_LIQ_SPOILS` | `[0]` = nudge, `[1]` = nudge prec, `[2]` = base ratio, `[3]` = ratio prec | Attacker bounty theft |

Config reading pattern:
```javascript
const configId = BigInt(ethers.keccak256(
  ethers.solidityPacked(["string", "string"], ["is.config", "KAMI_LIQ_ANIMOSITY"])
));
const raw = await valueComp.getValue(configId);
// Decode packed int32 array from raw uint256
```

### Animosity (Base Threshold)

Measures attacker Violence vs victim Harmony using a **Gaussian CDF** over
the log ratio:

```
combatRatio = ln(attackerViolence / victimHarmony)     // WAD precision (1e18)
base = GaussianCDF(combatRatio)                        // 0 to 1e18
animosity = base * KAMI_LIQ_ANIMOSITY[2] / 10^(18 + KAMI_LIQ_ANIMOSITY[3] - 6)
```

Result is in **1e6 precision** (proportion of max HP).

**Key insight**: Higher attacker Violence relative to victim Harmony → higher
animosity → easier to kill. The Gaussian CDF produces an S-curve:

| Violence : Harmony Ratio | CDF Output (~) | Animosity Behavior |
|---|---|---|
| 1:2 (defender advantage) | ~16% | Very low threshold — hard to kill |
| 1:1 (equal stats) | ~50% | Moderate threshold |
| 2:1 (attacker advantage) | ~84% | High threshold — easy to kill |
| 3:1+ (strong attacker) | ~95%+ | Nearly max threshold |

### Threshold Efficacy (Affinity Modifier)

The kill threshold is modified by **affinity matchup** between attacker's
**hand** affinity and victim's **body** affinity:

```
efficacy = KAMI_LIQ_THRESHOLD[2] + affinityShift + atkBonus - defBonus
```

Where `atkBonus` = `ATK_THRESHOLD_RATIO` on attacker, `defBonus` =
`DEF_THRESHOLD_RATIO` on victim.

Affinity combat triangle (rock-paper-scissors):

```
EERIE > SCRAP > INSECT > EERIE
NORMAL is neutral against all
```

| Matchup | Effect on Threshold |
|---|---|
| Attacker hand strong vs victim body | Threshold increases (easier kill) |
| Attacker hand weak vs victim body | Threshold decreases (harder kill) |
| Neutral / NORMAL | No modifier |

### Shift Modifier

```
shift = (ATK_THRESHOLD_SHIFT - DEF_THRESHOLD_SHIFT) * shiftPrecision
```

Skills in the Predator tree add `ATK_THRESHOLD_SHIFT` (attacker).
Skills in the Guardian tree add `DEF_THRESHOLD_SHIFT` (defender).

### Final Threshold

```
raw = animosity * efficacy + shift
threshold = raw * victimMaxHP / precision    // if raw > 0, else 0
```

## Recoil (Attacker HP Cost)

Killing is **not free**. The attacker takes recoil damage based on karma,
affinity, and the attacker's own harvest strain:

```
karma = GaussianCDF(ln(victimViolence / attackerHarmony)) * KAMI_LIQ_KARMA[2]
        / 10^(18 + KAMI_LIQ_KARMA[3] - 3)

nudge = max(0, KAMI_LIQ_RECOIL[0] / 10^KAMI_LIQ_RECOIL[1] + affinityShift)

boost = max(0, KAMI_LIQ_RECOIL[6] + DEF_RECOIL_BOOST + ATK_RECOIL_BOOST)

recoil = (karma + nudge) * attackerStrain * boost
         / 10^(KAMI_LIQ_RECOIL[1] + KAMI_LIQ_KARMA[3] + KAMI_LIQ_RECOIL[7])
```

Where:
- **Karma** = Gaussian CDF of victim Violence / attacker Harmony (1e3 precision).
  High-violence victims hit back harder
- **Nudge** = affinity-based modifier. Victim's **hand** vs attacker's **body**
  (reverse direction from threshold). Shifts: advantaged +1000, NORMAL-vs-NORMAL +400
- **Strain** = attacker's accumulated harvest strain (HP already lost to harvesting)
- **Boost** = from config + skill bonuses (DEF_RECOIL_BOOST currently unused)

## Loot Distribution

On a successful kill:

### Victim Gets (Salvage)

```
scaleFactor = 10^(KAMI_LIQ_SALVAGE[3] - KAMI_LIQ_SALVAGE[1])
ratio = KAMI_LIQ_SALVAGE[2] + (KAMI_LIQ_SALVAGE[0] + victimPower) * scaleFactor
        + DEF_SALVAGE_RATIO bonus
salvage = bounty * ratio / 10^(KAMI_LIQ_SALVAGE[1] + KAMI_LIQ_SALVAGE[3])
```

- Higher victim Power → more salvage (you keep more of your bounty)
- `DEF_SALVAGE_RATIO` bonus from Guardian tree skills increases salvage
- Victim Kami also gets XP = salvage amount
- Capped at 100% of bounty

### Attacker Gets (Spoils)

```
scaleFactor = 10^(KAMI_LIQ_SPOILS[3] - KAMI_LIQ_SPOILS[1])
ratio = KAMI_LIQ_SPOILS[2] + (KAMI_LIQ_SPOILS[0] + attackerPower) * scaleFactor
        + ATK_SPOILS_RATIO bonus
spoils = (bounty - salvage) * ratio / 10^(KAMI_LIQ_SPOILS[1] + KAMI_LIQ_SPOILS[3])
```

- Higher attacker Power → more spoils
- `ATK_SPOILS_RATIO` bonus from Predator tree skills increases spoils
- Spoils added to attacker's **harvest bounty** (not inventory)
- Attacker's account receives **1 Obol** (item 1015)
- Capped at 100% of remaining bounty

### Remaining Bounty
```
destroyed = bounty - salvage - spoils
```
Destroyed bounty is lost — benefits nobody.

## How to Execute

**Liquidate** — `system.harvest.liquidate` (Operator wallet)
```
executeTyped(uint256 victimHarvestID, uint256 killerKamiID)
```
- **Gas limit: 7,500,000 required** (complex PvP logic)
- Both Kamis must be `HARVESTING` on the same node
- Killer must own the attacking Kami

### Entity IDs

```
harvestId = keccak256("harvest", kamiEntityId)
```

## Cross-References

- HP projection: [state-reading.md](state-reading.md)
- Harvest strain (what drains HP): [harvesting.md](harvesting.md)
- Defensive skills: [leveling.md](leveling.md) (Guardian tree)
- Offensive skills: [leveling.md](leveling.md) (Predator tree)
