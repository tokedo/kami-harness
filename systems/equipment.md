# Equipment

Slot management and stat bonuses.

## How Equipment Works

Equipment items (`EQUIPMENT` type) are equippable to Kamis, granting stat
bonuses while worn. Each item occupies a named **slot**. Only one item per slot.

### Slot System

Each equipment item defines a slot via its `For` component (e.g.,
`Kami_Pet_Slot`). The slot name determines which equipment competes for the
same position.

**Capacity**: each Kami has a **maximum number of equipment slots** it can fill.

```
capacity = 1 + EQUIP_CAPACITY_SHIFT bonus
```

Default capacity is **1**. Currently no skill or item grants additional
capacity — all Kamis can equip exactly 1 item.

### Replacing Equipment

If you equip a new item into an **already occupied slot**, the old item is
automatically unequipped first (returned to inventory). This doesn't consume
additional capacity — it's a swap.

If you equip into a **new slot** (different slot name), it consumes 1 capacity.
With default capacity of 1, this means you can only fill 1 unique slot.

## Equip Process

System: `system.kami.equip`

1. Kami must be `RESTING`
2. Item must be `EQUIPMENT` type and enabled
3. If slot occupied → auto-unequip old item (bonuses cleared, item returned)
4. If new slot → check capacity
5. Consumes 1 item from inventory
6. Creates equipment instance entity
7. Applies item's `EQUIP` bonuses to the Kami

## Unequip Process

System: `system.kami.unequip`

1. Kami must be `RESTING`
2. Clears all bonuses from that slot
3. Removes equipment instance entity
4. Returns 1 item to inventory

Note: unequip takes a **slot name** (string), not an item index.

## Bonus Effects

Equipment bonuses are applied via the bonus system. Common effects:

| Effect | What It Does |
|---|---|
| Stat shifts | +Health, +Power, +Violence, +Harmony |
| Stat boosts | % multiplier on stats |
| Harvest bonuses | Fertility boost, intensity boost, bounty boost |
| Defense bonuses | Threshold shift/ratio |
| Strain reduction | Negative strain boost |
| Cooldown reduction | Negative cooldown shift |

Bonuses are **automatically cleared** when the item is unequipped (tagged with
`ON_UNEQUIP_{SLOT}` end type).

### Stat Effects

- Harmony reduces strain and improves liquidation defense.
- Power increases harvest output (Fertility).
- Strain reduction extends harvest duration.
- Violence increases the kill threshold.

Equipment can only be changed while the Kami is `RESTING`; a `HARVESTING` Kami
must stop its harvest session first, which ends that session.

See [catalogs/items.csv](../catalogs/items.csv) for equipment items and their
stat bonuses.

## How to Execute

**Equip** — `system.kami.equip` (Operator wallet)
```
executeTyped(uint256 kamiID, uint32 itemIndex)
```
- Kami must be `RESTING`
- Item must be in inventory and have `EQUIPMENT` type

**Unequip** — `system.kami.unequip` (Operator wallet)
```
executeTyped(uint256 kamiID, string slot)
```
- Kami must be `RESTING`
- Pass the slot name string (e.g., `"Kami_Pet_Slot"`)

## Reading Equipment State

See [state-reading.md](state-reading.md) for querying equipped items on a Kami.

## Cross-References

- Item catalog: [catalogs/items.csv](../catalogs/items.csv)
- Stat formulas (how boosts apply): [accounts.md](accounts.md)
- Skill bonuses (alternative to equipment): [leveling.md](leveling.md)
