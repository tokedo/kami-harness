# Crafting & Items

How to craft items, use consumables, and manage inventory.

## Crafting

Convert input items → output items via predefined recipes. Costs stamina,
grants account XP.

### Process

```
CraftSystem.execute(recipeIndex, amount)
```

1. Check recipe requirements (level, location, items owned)
2. Deduct stamina: `staminaCost * amount`
3. Consume inputs: `inputAmount[i] * amount` for each input
4. Produce outputs: `outputAmount[i] * amount` for each output
5. Grant account XP: `recipeXP * amount`

Batch crafting: the `amount` parameter multiplies everything.

Crafting draws from the same stamina pool as movement. Quest objectives can
track crafting completions via `CRAFT_ITEM`.

### Recipe Data

See [catalogs/recipes.csv](../catalogs/recipes.csv) for all recipes:
- Input items and quantities
- Output items and quantities
- Stamina cost
- XP reward
- Requirements (level, room, etc.)

## Item Types

| Type | Behavior |
|---|---|
| Base items | Simple holdable items (Musu, crafting materials) |
| `EQUIPMENT` | Equippable, grants stat bonuses (see [equipment.md](equipment.md)) |
| `LOOTBOX` | Opens via droptable commit-reveal |
| Consumables | Used on Kami or account for effects |

### Key Items

| Item | Index | Purpose |
|---|---|---|
| Musu | 1 | Base currency |
| Gacha Ticket | 10 | Mint new Kamis |
| Reroll Token | 11 | Exchange Kami for random one |
| Onyx Shards | 100 | Revive dead Kamis (33 per revive), premium currency |
| Obols | 1015 | Earned from liquidations |
| Respec Potion | 11403 | Reset all skills on a Kami |

### Item Flags

- `NOT_TRADABLE` — cannot be transferred between players
- `ITEM_UNBURNABLE` — cannot be burned/destroyed

## Using Items

### On Your Kami

System: `system.kami.use.item`
```
executeTyped(uint256 kamiID, uint32 itemIndex)
```

- Kami must be owned by you and in same room
- Kami must be off cooldown
- Consumes 1 item
- Effects: healing (sync HP), stat buffs (shift), temporary bonuses
- **Resets harvest intensity**

### On Enemy Kami (Cast)

System: `system.kami.cast.item`
```
executeTyped(uint256 targetKamiID, uint32 itemIndex)
```

- Target must be in same room
- Costs **10 stamina**
- Items must have `ENEMY_KAMI` shape

### On Account

System: `system.account.use.item`
```
executeTyped(uint32 itemIndex, uint256 amount)
```

- Items with `ACCOUNT` shape
- Can use multiple at once (`amount > 1`)
- Effects: stamina, bonuses, etc.

### Opening Lootboxes

Lootbox items create a droptable commit when used. Reveal in a separate
transaction (same as scavenging reveals):
1. Use the lootbox item → commit created
2. Call `system.droptable.reveal` with the commit ID → items distributed

## Burning Items

System: `system.item.burn`
```
executeTyped(uint32[] indices, uint256[] amounts)
```

- Permanently destroys items
- Required for some quest objectives ("give item" quests track `ITEM_BURN`)
- Cannot burn items flagged `ITEM_UNBURNABLE`

## Transferring Items

System: `system.item.transfer`
```
executeTyped(uint32[] indices, uint256[] amounts, uint256 targetAccountID)
```

- Transfer fee: **15 Musu per item type** (not per unit)
- Cannot transfer items flagged `NOT_TRADABLE`

## Inventory Management

### Inventory Queries

See [state-reading.md](state-reading.md) for reading inventory balances.

## Cross-References

- Recipe catalog: [catalogs/recipes.csv](../catalogs/recipes.csv)
- Item catalog: [catalogs/items.csv](../catalogs/items.csv)
- Stamina management: [accounts.md](accounts.md)
- Equipment: [equipment.md](equipment.md)
- Scavenge/droptable reveals: [scavenging.md](scavenging.md)
