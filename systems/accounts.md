# Accounts, Stats & Cooldowns

Stamina, cooldowns, stat formulas, and the owner/operator wallet model.

## Stat System

All stats (Kami and Account) use the same struct:

```
Stat { base, shift, boost, sync }
```

### Effective (Total) Stat Value

```
Total = max(0, floor((1000 + boost) * (base + shift) / 1000))
```

| boost | Effect |
|---|---|
| 0 | No change (1.0x) |
| 500 | +50% (1.5x) |
| 1000 | +100% (2.0x) |
| -500 | -50% (0.5x) |

### Where Modifiers Come From

| Modifier | Source |
|---|---|
| `base` | Set at creation (traits). Never changes |
| `shift` | Skills (`STAT_{TYPE}_SHIFT`), equipment, consumable items |
| `boost` | Skills (`STAT_{TYPE}_BOOST`), equipment, temporary buffs |
| `sync` | Current depletable value (HP, stamina, slots). Changes on actions |

### Kami Stats

| Stat | Role | Depletable? |
|---|---|---|
| Health | HP pool. Drained by harvest strain, healed by resting | Yes (`sync` = current HP) |
| Power | Scales harvest Fertility (base income rate) | No |
| Violence | Scales harvest Intensity + liquidation attack power | No |
| Harmony | Reduces strain, speeds healing, defends against liquidation | No |
| Slots | Equipment capacity | Yes (`sync` = available slots) |

### Account Stats

| Stat | Role | Depletable? |
|---|---|---|
| Stamina | Gates movement and crafting | Yes (`sync` = current stamina) |

## Stamina System

### Configuration

| Parameter | Production Value |
|---|---|
| Max stamina (base) | **100** |
| Recovery period | **60 seconds** per point |
| Movement cost | **5** per room move |
| Movement XP | **5** per move |

### Recovery

Stamina regenerates passively over time (lazy-synced):

```
timePassed = now - lastActionTimestamp
recovery = floor(timePassed / 60)
currentStamina = min(sync + recovery, maxStamina)
```

Partial periods are lost (rounds down).

| Stamina State | Time to Full |
|---|---|
| From 0 | ~100 minutes |
| From 50 | ~50 minutes |
| From 95 | ~5 minutes |

### Stamina Budget

With 100 max stamina:
- **20 room moves** from full (5 per move)
- Crafting also costs stamina (per recipe)

## Cooldowns

After most Kami actions, a cooldown prevents the next action.

### Base Cooldown

```
cooldown = max(0, 180 + STND_COOLDOWN_SHIFT bonus)
```

- **Base**: 180 seconds (3 minutes)
- Skills in the Predator tree can reduce cooldown (negative `CS` bonus)
- Cooldown cannot go below 0

### What Triggers Cooldown

- Harvest start, stop, collect
- Level up
- Equip/unequip
- Use item on Kami

### Cooldown Check

A Kami is on cooldown when `block.timestamp < TimeNext` component value.

```
remaining = cooldownEnd - now
```

If remaining > 0, the Kami is still on cooldown.

## Account XP

Accounts have their own XP pool, separate from Kami XP:
- **Movement**: 5 XP per room move
- **Crafting**: XP per recipe (varies)
- **Quest rewards**: some quests grant account XP

> Account XP has **no level-up mechanism**. Only Kamis level up.

## Owner/Operator Wallet Model

Two wallets per player:

| Wallet | Purpose | Actions |
|---|---|---|
| **Owner** | High-security. Holds ETH + tokens | Register account, trade (P2P + Kami market), mint, ERC-20 approvals |
| **Operator** | Day-to-day gameplay | Harvest, move, equip, quest, craft, use items, level up, sacrifice |

The operator is set by the owner via `system.account.set.operator`.

### Entity ID

Account entity ID = `uint256(ownerAddress)` — derived directly from the
owner wallet address.

### Registration

System: `system.account.register` (Owner wallet)
```
executeTyped(address operator, string name)
```
- Name: max 16 characters, globally unique
- Starting room: 1 (Misty Riverside)
- Starting stamina: 100

## How to Execute

**Move** — `system.account.move` (Operator)
```
executeTyped(uint32 toRoomIndex)
```
Costs 5 stamina, grants 5 account XP.

**Set operator** — `system.account.set.operator` (Owner)
```
executeTyped(address newOperator)
```

## Cross-References

- Stamina projection: [state-reading.md](state-reading.md)
- Movement and rooms: [rooms.md](rooms.md)
- HP projection (depletable stat): [health.md](health.md)
- Cooldown-reducing skills: [leveling.md](leveling.md) (Predator tree)
- Harvest strain (HP drain): [harvesting.md](harvesting.md)
