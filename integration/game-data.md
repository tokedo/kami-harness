> **Doc Class:** Core Resource
> **Canonical Source:** On-chain registries/components on Yominet plus official Kamigotchi deployment data (`Asphodel-OS/kamigotchi`).
> **Freshness Rule:** Treat this page as a mirror; re-verify mutable values against canonical sources .

# Game Data Reference

Lookup tables for game indices used across Kamigotchi systems. These values come from the deployment data.

> **Note:** Game data is defined in CSV sheets and deployed on-chain via admin systems. The tables below reflect the current live deployment. CSV file paths referenced below are internal to the Kamigotchi source repository and are not accessible to third-party developers. For the most up-to-date data, query the on-chain components directly.
>
> **Freshness authority:** verify against on-chain canonical sources.

---

## Items

Items are identified by a `uint32` index. The on-chain entity ID for an item is `keccak256("registry.item", index)`.

### Currencies & Tickets

| Index | Name | Type | Description |
|-------|------|------|-------------|
| 1 | MUSU | Misc | Kamigotchi kurrency — the primary in-game currency |
| 2 | VIPP | Misc | VIP Points token — can be burned at Forest Hut (room 65) for VIP benefits |
| 10 | Gacha Ticket | Misc | Redeemable for one Kami at the vending machine |
| 11 | Reroll Ticket | Misc | Allows you to reroll a Kami once |
| 100 | Onyx Shard | ERC20 | In-game form of $ONYX (1 ONYX = 100 Onyx Shards). Deposited/withdrawn via `system.erc20.portal` — see [Chain Configuration](chain.md#onyx-shards) |
| 103 | ETH | ERC20 | In-game wrapped ETH balance. Deposited via `system.erc20.portal`. |

### Raw Materials

| Index | Name | Type | Rarity |
|-------|------|------|--------|
| 1001 | Wooden Stick | Material | Common |
| 1002 | Stone | Material | Common |
| 1003 | Plastic Bottle | Material | Uncommon |
| 1004 | Pine Cone | Material | Uncommon |
| 1005 | Scrap Metal | Material | Common |
| 1006 | Glass Jar | Material | Rare |
| 1007 | Red Amber Crystal | Material | Epic |
| 1010 | Black Poppy | Material | Rare |
| 1011 | Daffodil | Material | Uncommon |
| 1012 | Mint | Material | Epic |
| 1013 | Sanguine Shroom | Material | Uncommon |
| 1014 | Chalkberry | Material | Uncommon |
| 1015 | Obol | Misc | Uncommon |
| 1016 | Dried Stems | Material | Common |
| 1017 | Patinated Pipe | Material | Common |
| 1018 | Cigarette Butt | Material | Common |
| 1019 | Otherworld Coin | Material | Uncommon |
| 1020 | Bone Chunk | Material | Common |
| 1021 | Irradiated Root | Material | Rare |

### Processed Materials

| Index | Name | Type | Rarity |
|-------|------|------|--------|
| 1102 | Empty Cup | Material | Uncommon |
| 1103 | Microplastics | Material | Uncommon |
| 1104 | Pine Pollen | Material | Uncommon |
| 1107 | Powdered Red Amber | Material | Epic |
| 1110 | Black Poppy Extract | Material | Rare |
| 1111 | Essence of Daffodil | Material | Uncommon |
| 1112 | Shredded Mint | Material | Epic |
| 1113 | Sanguineous Powder | Material | Uncommon |
| 1114 | Berry Chalk | Material | Uncommon |
| 1121 | Pallid Root Extract | Material | Rare |
| 1201 | Holy Syrup | Material | Rare |
| 1202 | Resin Tincture | Material | Uncommon |
| 1203 | Fuliginous Ooze | Material | Epic |
| 1301 | Ashlar | Material | Uncommon |
| 1302 | Timber | Material | Uncommon |
| 1303 | Ingot | Material | Uncommon |

### Essences

| Index | Name | Type | Rarity |
|-------|------|------|--------|
| 6001 | Essence of Hearing | Material | Rare |
| 6002 | Essence of Smell | Material | Rare |
| 6003 | Essence of Sight | Material | Rare |
| 6004 | Essence of Taste | Material | Rare |
| 6005 | Essence of Touch | Material | Rare |
| 6006 | Essence of Thought | Material | Rare |
| 6007 | Pure Essence | Material | Epic |

### Kami Consumables (selected)

| Index | Name | Type | Effect |
|-------|------|------|--------|
| 11001 | Red Ribbon Gummy | Revive | Revive + HP+10 |
| 11003 | Djed Pillar | Consumable | Revive + HP+5 |
| 11004 | Pale Potion | Potion | Revive + HP+75 |
| 11011 | Holy Dust | Misc | Rename a Kami at the shrine |
| 11020 | Cleaning Fluid | Potion | Clear all effects |
| 11110 | Gaokerena Mochi | Food | Permanent Health +10 |
| 11120 | Sunset Apple Mochi | Food | Permanent Power +1 |
| 11130 | Kami Mochi | Food | Permanent Violence +1 |
| 11140 | Mana Mochi | Food | Permanent Harmony +1 |
| 11201 | XP Candy (Small) | Food | HP+5, XP+25 |
| 11301 | Maple-Flavor Ghost Gum | Food | HP+25 |
| 11302 | Cheeseburger | Food | HP+50 |
| 11304 | Gakki Cookie Sticks | Food | HP+100 |
| 11311 | Resin | Food | HP+35 |
| 11312 | Honeydew Scale | Food | HP+75 |
| 11313 | Golden Apple | Food | HP+150 |
| 11401 | XP Potion | Food | XP+1000 |
| 11403 | Respec Potion | Misc | Reset skill points |
| 11404 | Grace Potion | Food | Strain -25% next harvest |
| 11405 | Bless Potion | Food | Bounty +25% next harvest |
| 11409 | Energy Drink | Food | Cooldown -30s |

### Operator Consumables (selected)

| Index | Name | Type | Effect |
|-------|------|------|--------|
| 21001 | Giftbox | Lootbox | Basic lootbox |
| 21002 | Citizen Giftbox | Lootbox | Passport-tier lootbox |
| 21003 | Wonder Egg | Lootbox | Surprise lootbox |
| 21004 | Booster Pack | Lootbox | Spell Card booster |
| 21005 | Mochibox | Lootbox | Contains one Mochi |
| 21201 | Ice Cream | Food | Stamina +20 |
| 21202 | Better Ice Cream | Food | Stamina +40 |
| 21203 | Best Ice Cream | Food | Stamina +80 |

### Tools

| Index | Name | Type | Rarity |
|-------|------|------|--------|
| 23100 | Spice Grinder | Tool | Rare |
| 23101 | Portable Burner | Tool | Rare |
| 23102 | Screwdriver | Tool | Epic |

### Key Items (selected)

| Index | Name | Description |
|-------|------|-------------|
| 100001 | Astrolabe Disk | Golden disk resembling an astrolabe tympan |
| 100004 | Aetheric Sextant | Divines things beyond mortal perception |
| 100005 | Pyramid Engine | Ancient Egyptian-style electrical generator |
| 100010 | Dowsing Rod | Senses traces of crystal power |

> **Total items in deployment:** ~130+. The full list is defined in `packages/contracts/deployment/world/data/items/items.csv`.

---

## Rooms

Rooms are identified by a `uint32` index. On-chain entity ID: `keccak256("room", roomIndex)`.

| Index | Name | X | Y | Z | Special Exits |
|-------|------|---|---|---|---------------|
| 1 | Misty Riverside | 3 | 1 | 1 | 20 |
| 2 | Tunnel of Trees | 3 | 3 | 1 | 13 |
| 3 | Torii Gate | 3 | 4 | 1 | — |
| 4 | Vending Machine | 3 | 6 | 1 | — |
| 5 | Restricted Area | 3 | 9 | 1 | — |
| 6 | Labs Entrance | 4 | 10 | 1 | 28 |
| 9 | Forest: Old Growth | 5 | 8 | 1 | — |
| 10 | Forest: Insect Node | 5 | 5 | 1 | — |
| 11 | Temple by the Waterfall | 6 | 11 | 1 | 24, 15 |
| 12 | Scrap Confluence | 1 | 6 | 1 | — |
| 13 | Convenience Store | 4 | 3 | 2 | 2 |
| 15 | Temple Cave | 5 | 7 | 3 | 11 |
| 16 | Techno Temple | 6 | 7 | 3 | — |
| 18 | Cave Crossroads | 5 | 6 | 3 | — |
| 19 | Temple of the Wheel | 2 | 4 | 3 | 59 |
| 25 | Lost Skeleton | 6 | 9 | 1 | — |
| 26 | Trash-Strewn Graves | 2 | 8 | 1 | — |
| 29 | Misty Forest Path | 3 | 2 | 1 | — |
| 30 | Scrapyard Entrance | 3 | 5 | 1 | — |
| 31 | Scrapyard Exit | 3 | 8 | 1 | — |
| 32 | Road To Labs | 3 | 10 | 1 | — |
| 33 | Forest Entrance | 4 | 8 | 1 | — |
| 34 | Deeper Into Scrap | 2 | 6 | 1 | — |
| 35 | Elder Path | 5 | 6 | 1 | — |
| 36 | Parting Path | 5 | 9 | 1 | — |
| 37 | Hollow Path | 6 | 10 | 1 | — |
| 47 | Scrap Paths | 3 | 7 | 1 | — |
| 48 | Murky Forest Path | 5 | 7 | 1 | — |
| 49 | Clearing | 7 | 9 | 1 | — |
| 50 | Ancient Forest Entrance | 6 | 5 | 1 | — |
| 51 | Scrap-Littered Undergrowth | 7 | 5 | 1 | — |
| 52 | Airplane Crash | 8 | 5 | 1 | 54 |
| 53 | Blooming Tree | 7 | 4 | 1 | — |
| 54 | Plane Interior | 8 | 5 | 2 | 52 |
| 55 | Shady Path | 4 | 3 | 1 | — |
| 56 | Butterfly Forest | 5 | 3 | 1 | — |
| 57 | River Crossing | 6 | 3 | 1 | — |
| 58 | Mouth of Scrap | 1 | 5 | 1 | — |
| 59 | Black Pool | 1 | 4 | 1 | 19 |
| 60 | Scrap Trees | 5 | 1 | 1 | — |
| 61 | Musty Forest Path | 7 | 1 | 1 | — |
| 62 | Centipedes | 8 | 1 | 1 | — |
| 63 | Deeper Forest Path | 6 | 2 | 1 | — |
| 64 | Burning Room | 5 | 5 | 2 | 65 |
| 65 | Forest Hut | 6 | 1 | 1 | 64 |
| 66 | Marketplace | 2 | 2 | 1 | — |
| 67 | Boulder Tunnel | 4 | 6 | 3 | — |
| 68 | Slippery Pit | 3 | 6 | 3 | — |
| 69 | Lotus Pool | 3 | 7 | 3 | — |
| 70 | Still Stream | 2 | 7 | 3 | — |
| 71 | Shabby Deck | 1 | 7 | 3 | — |
| 72 | Hatch to Nowhere | 1 | 6 | 3 | 88 |
| 73 | Broken Tube | 1 | 5 | 3 | — |
| 74 | Engraved Door | 2 | 5 | 3 | — |
| 75 | Flood Mural | 3 | 5 | 3 | — |
| 76 | Fungus Garden | 5 | 5 | 3 | — |
| 77 | Thriving Mushrooms | 5 | 4 | 3 | — |
| 78 | Toadstool Platforms | 5 | 3 | 3 | — |
| 79 | Abandoned Campsite | 5 | 2 | 3 | — |
| 80 | Radiant Crystal | 6 | 2 | 3 | — |
| 81 | Flower Mural | 7 | 2 | 3 | — |
| 82 | Geometric Cliffs | 7 | 3 | 3 | — |
| 83 | Canyon Bridge | 7 | 4 | 3 | — |
| 84 | Reinforced Tunnel | 6 | 4 | 3 | — |
| 85 | Giant's Palm | 7 | 5 | 3 | — |
| 86 | Guardian Skull | 8 | 5 | 3 | — |
| 87 | Sacrarium | 8 | 6 | 3 | — |
| 88 | Treasure Hoard | 3 | 1 | 4 | 72 |
| 89 | Trophies of the Hunt | 2 | 1 | 4 | — |
| 90 | Scenic View | 1 | 1 | 4 | — |

> **Total rooms:** 68. Room indices are **not sequential** — gaps exist (e.g., 7, 8, 14, 17, 20–24, 27–28).

### Movement Rules

Rooms are connected by **coordinate adjacency**: two rooms are adjacent if they differ by exactly 1 on a single axis (X or Y) and share the same Z-level. Movement is only possible between adjacent rooms or via **special exits** (listed in the table above), which can connect rooms across Z-levels or non-adjacent coordinates.

**Pathfinding for agents:** Build a graph where edges connect rooms that are coordinate-adjacent (same Z, ΔX or ΔY = 1, other axis unchanged) plus all special exit pairs. Some exits are gated by quest completion or items (e.g., caves require completing MSQ035).

```javascript
// Check if two rooms are adjacent (same Z, differ by 1 on exactly one axis)
function isAdjacent(roomA, roomB) {
  if (roomA.z !== roomB.z) return false;
  const dx = Math.abs(roomA.x - roomB.x);
  const dy = Math.abs(roomA.y - roomB.y);
  return (dx === 1 && dy === 0) || (dx === 0 && dy === 1);
}
```

---

## Harvest Nodes

Nodes are the harvestable locations within rooms. Each node shares an index with its room. On-chain entity ID: `keccak256("node", nodeIndex)`.

| Index | Name | Affinity | Yield | Level Limit | Scav Cost |
|-------|------|----------|-------|-------------|-----------|
| 1 | Misty Riverside | Eerie | MUSU | 15 | 100 |
| 2 | Tunnel of Trees | Normal | MUSU | 15 | 100 |
| 3 | Torii Gate | Normal | MUSU | 15 | 100 |
| 5 | Restricted Area | Normal | MUSU | — | 100 |
| 6 | Labs Entrance | Eerie | MUSU | — | 100 |
| 9 | Forest: Old Growth | Insect | MUSU | — | 200 |
| 10 | Forest: Insect Node | Insect | MUSU | — | 200 |
| 12 | Scrap Confluence | Scrap | MUSU | — | 500 |
| 15 | Temple Cave | Scrap | MUSU | — | 100 |
| 16 | Techno Temple | Eerie, Scrap | MUSU | — | 500 |
| 18 | Cave Crossroads | Insect | MUSU | — | 200 |
| 19 | Temple of the Wheel | Eerie, Scrap | MUSU | — | 300 |
| 25 | Lost Skeleton | Eerie | MUSU | — | 200 |
| 26 | Trash-Strewn Graves | Eerie | MUSU | — | 100 |
| 29 | Misty Forest Path | Insect | MUSU | 15 | 100 |
| 30 | Scrapyard Entrance | Scrap | MUSU | 15 | 100 |
| 31 | Scrapyard Exit | Scrap | MUSU | — | 100 |
| 32 | Road To Labs | Normal | MUSU | — | 100 |
| 33 | Forest Entrance | Normal | MUSU | — | 200 |
| 34 | Deeper Into Scrap | Scrap | MUSU | — | 300 |
| 35 | Elder Path | Normal | MUSU | — | 200 |
| 36 | Parting Path | Insect | MUSU | — | 200 |
| 37 | Hollow Path | Normal | MUSU | — | 200 |
| 47 | Scrap Paths | Scrap | MUSU | — | 100 |
| 48 | Murky Forest Path | Insect | MUSU | — | 200 |
| 49 | Clearing | Normal | MUSU | — | 300 |
| 50 | Ancient Forest Entrance | Insect | MUSU | — | 200 |
| 51 | Scrap-Littered Undergrowth | Insect | MUSU | — | 300 |
| 52 | Airplane Crash | Eerie | MUSU | — | 300 |
| 53 | Blooming Tree | Eerie | MUSU | — | 300 |

> **Total nodes:** 64. Shown above are the first 30; for the full list see `packages/contracts/deployment/world/data/rooms/nodes.csv`. Node affinity affects harvest efficacy — matching a Kami's body/hand affinity to the node affinity yields bonuses.
>
> **Yield Index:** Most nodes use YieldIndex=1 (yields MUSU, item index 1). The following nodes use YieldIndex=2, which yields **VIPP** (VIP Points token, item index 2 — can be burned at Forest Hut room 65): 18 (Cave Crossroads), 60 (Scrap Trees), 61 (Musty Forest Path), 62 (Centipedes), 63 (Deeper Forest Path), 65 (Forest Hut), 73 (Broken Tube), 75 (Flood Mural), 79 (Abandoned Campsite), 83 (Canyon Bridge), 88 (Treasure Hoard).

---

## Skills

Skills are organized in four trees with six tiers each (tiers 1–6). The on-chain config defines 8 tier slots (0–7), but tiers 0 and 7 have no deployed skills in the current version. Each skill has a `uint32` index.

### Predator Tree

| Index | Name | Tier | Max | Cost | Effect |
|-------|------|------|-----|------|--------|
| 111 | Aggression | 1 | 5 | 1 | Violence +1 |
| 112 | Grit | 1 | 5 | 1 | Health +10 |
| 113 | Mercenary | 1 | 5 | 1 | Attack Success Rate +2% |
| 121 | Professional | 2 | 5 | 1 | Attack Type Rate +5% |
| 122 | Cruelty | 2 | 5 | 1 | Attack Type Shift +2% |
| 123 | Sniper | 2 | 5 | 1 | Cooldown -10s |
| 131 | Warmonger | 3 | 1 | 1 | Violence +3 |
| 132 | Vampire | 3 | 1 | 1 | Defense Success Rate +6% |
| 133 | Bandit | 3 | 1 | 1 | Attack Success Rate +6% |
| 141 | Hungry | 4 | 5 | 1 | Power +1 |
| 142 | Brutality | 4 | 5 | 1 | Attack Type Shift +2% |
| 143 | Marksman | 4 | 5 | 1 | Cooldown -10s |
| 151 | Specialist | 5 | 5 | 1 | Attack Type Rate +5% |
| 152 | First Aid | 5 | 5 | 1 | Defense Success Rate +2% |
| 153 | Bounty Hunter | 5 | 5 | 1 | Attack Success Rate +2% |
| 161 | Warlord | 6 | 1 | 1 | Violence +5 |
| 162 | Lethality | 6 | 1 | 1 | Attack Type Shift +10% |
| 163 | Assassin | 6 | 1 | 1 | Cooldown -50s |

### Enlightened Tree

| Index | Name | Tier | Max | Cost | Effect |
|-------|------|------|-----|------|--------|
| 211 | Self Care | 1 | 5 | 1 | Rest Max Bonus +5% |
| 212 | Cardio | 1 | 5 | 1 | Health +10 |
| 213 | Good Constitution | 1 | 5 | 1 | Harvest Fertility Bonus +6% |
| 221 | Focus | 2 | 5 | 1 | Harvest Bounty Bonus +4% |
| 222 | Meditative Breathing | 2 | 5 | 1 | Defense Type Shift +2% |
| 223 | Concentration | 2 | 5 | 1 | Strain Bonus -2.5% |
| 231 | Sleep Hygiene | 3 | 1 | 1 | Rest Max Bonus +15% |
| 232 | Warmup Exercise | 3 | 1 | 1 | Harvest Intensity +15/hr |
| 233 | Advanced Mewing | 3 | 1 | 1 | Harvest Fertility Bonus +18% |
| 241 | Momentum | 4 | 5 | 1 | Harvest Bounty Bonus +4% |
| 242 | Therapy | 4 | 5 | 1 | Defense Type Shift +2% |
| 243 | Endurance | 4 | 5 | 1 | Strain Bonus -2.5% |
| 251 | Regeneration | 5 | 5 | 1 | Rest Max Bonus +5% |
| 252 | Workout Routine | 5 | 5 | 1 | Harvest Intensity +5/hr |
| 253 | Productivity | 5 | 5 | 1 | Harvest Fertility Bonus +6% |
| 261 | Wu Wei | 6 | 1 | 1 | Harvest Bounty Bonus +20% |
| 262 | Spin Class | 6 | 1 | 1 | Health +50 |
| 263 | Immortality | 6 | 1 | 1 | Strain Bonus -12.5% |

### Guardian Tree

| Index | Name | Tier | Max | Cost | Effect |
|-------|------|------|-----|------|--------|
| 311 | Defensiveness | 1 | 5 | 1 | Harmony +1 |
| 312 | Toughness | 1 | 5 | 1 | Health +10 |
| 313 | Patience | 1 | 5 | 1 | Harvest Intensity +5/hr |
| 321 | Meticulous | 2 | 5 | 1 | Defense Type Rate +5% |
| 322 | Vigor | 2 | 5 | 1 | Health +10 |
| 323 | Armor | 2 | 5 | 1 | Defense Type Shift +2% |
| 331 | Anxiety | 3 | 1 | 1 | Harmony +3 |
| 332 | Die Hard | 3 | 1 | 1 | Strain Bonus -7.5% |
| 333 | Loyalty | 3 | 1 | 1 | Harvest Intensity +15/hr |
| 341 | Flawless | 4 | 5 | 1 | Defense Type Rate +5% |
| 342 | Dedication | 4 | 5 | 1 | Harvest Intensity +5/hr |
| 343 | Shielding | 4 | 5 | 1 | Defense Type Shift +2% |
| 351 | Powerhouse | 5 | 5 | 1 | Violence +1 |
| 352 | Hefty | 5 | 5 | 1 | Health +10 |
| 353 | Fortress | 5 | 5 | 1 | Defense Type Shift +2% |
| 361 | Neurosis | 6 | 1 | 1 | Harmony +5 |
| 362 | Undying | 6 | 1 | 1 | Strain Bonus -12.5% |
| 363 | Obsession | 6 | 1 | 1 | Harvest Intensity +25/hr |

### Harvester Tree

| Index | Name | Tier | Max | Cost | Effect |
|-------|------|------|-----|------|--------|
| 411 | Acquisitiveness | 1 | 5 | 1 | Power +1 |
| 412 | Mogging | 1 | 5 | 1 | Health +10 |
| 413 | Greed | 1 | 5 | 1 | Harvest Bounty Bonus +4% |
| 421 | Wide Portfolio | 2 | 5 | 1 | Strain Bonus -2.5% |
| 422 | Side Hustles | 2 | 5 | 1 | Harvest Fertility Bonus +6% |
| 423 | Hedging | 2 | 5 | 1 | Defense Success Rate +2% |
| 431 | Technical Analysis | 3 | 1 | 1 | Power +3 |
| 432 | Daylight Savings | 3 | 1 | 1 | Defense Type Shift +6% |
| 433 | Leverage | 3 | 1 | 1 | Harvest Bounty Bonus +12% |
| 441 | Opportunist | 4 | 5 | 1 | Violence +1 |
| 442 | Trading Courses | 4 | 5 | 1 | Harvest Fertility Bonus +6% |
| 443 | Index Funds | 4 | 5 | 1 | Harmony +1 |
| 451 | Time in the Market | 5 | 5 | 1 | Strain Bonus -2.5% |
| 452 | Looping | 5 | 5 | 1 | Health +10 |
| 453 | Stimulants | 5 | 5 | 1 | Harvest Bounty Bonus +4% |
| 461 | Intelligent Investor | 6 | 1 | 1 | Power +5 |
| 462 | Paid Groupchat | 6 | 1 | 1 | Harvest Fertility Bonus +30% |
| 463 | Coward | 6 | 1 | 1 | Defense Success Rate +10% |

> **Total skills:** 72 (18 per tree × 4 trees). Tier 3 and Tier 6 skills are mutually exclusive within their row (pick 1 of 3). Each skill costs 1 skill point per level. Skill data is in `packages/contracts/deployment/world/data/skills/skills.csv`.

---

## Quests

Quests are identified by a `uint32` index. The on-chain registry entity ID is `keccak256("registry.quest", questIndex)`. When a player accepts a quest, the instance entity ID is `keccak256("quest.instance", questIndex, accountEntityId)`.

### Main Story Quests (MSQ)

| Index | Title | Prerequisite | Objective | Rewards |
|-------|-------|--------------|-----------|---------|
| 1 | Welcome to Kamigotchi World | — | *(tutorial — explore the UI)* | 2× Agency Reputation |
| 2 | Beginning Your Journey | MSQ 1 | Move 3 Times | 1× "Neith's River of Life" Spell Card |
| 3 | Your First Kami | MSQ 2 | Own 1 Kamigotchi | 6× Agency Reputation |
| 4 | What Kami Do: Harvesting | MSQ 3 | Harvest for >5 minutes | 1× "Cultivation I" Spell Card |
| 5 | What Kami Do: Scavenging | MSQ 4 | Scavenge 1 Item | 4× Agency Reputation |
| 6 | What Kami Do: Liquidating | MSQ 5 | Liquidate another Kamigotchi | 4× Agency Reputation |
| 7 | Making $MUSU | MSQ 4 | Collect 500 $MUSU | 4× Agency Rep, 1× "Cultivation I" |
| 8 | Supporting Local Businesses | MSQ 7 | Buy something from any vendor | 2× Agency Reputation |
| 9 | Building a Reputation | MSQ 8 | Give 3 Scrap Metal | 6× Agency Rep, 1× "Paeon's Field of Flowers" |
| 10 | KW and You: Having a Normal One | MSQ 9 | Scavenge in 3 Normal-type rooms | 4× Agency Rep, 1× "Neith's River of Life" |
| 11 | KW and You: That Eerie Feeling | MSQ 10 | Scavenge in 3 Eerie-type rooms | 4× Agency Reputation |
| 12 | KW and You: Insects in the Miasma | MSQ 11 | Scavenge in 3 Insect-type rooms | 4× Agency Reputation |
| 13 | KW and You: Tossed in the Scrap Heap | MSQ 12 | Scavenge in 3 Scrap-type rooms | 4× Agency Rep, 1× "Neith's River of Life" |
| 14 | Identifying Materials: Wood | MSQ 13 | Give 5 Wooden Sticks | 4× Agency Reputation |
| 15 | Identifying Materials: Stone | MSQ 14 | Give 5 Stone | 4× Agency Reputation |
| 16 | Identifying Materials: Metal | MSQ 15 | Give 5 Scrap Metal | 4× Agency Reputation |
| 17 | Exploring Other Options | MSQ 16 | Move 100 times | 2× Agency Rep, 1× "Neith's River of Life" |
| 18 | Harvesting Data I | MSQ 17 | Harvest >720 min in Scrap Confluence | 4× Agency Rep, 1× "Paeon's Field of Flowers" |
| 19 | Harvesting Data II | MSQ 18 | Harvest >720 min at Labs Entrance | 4× Agency Rep, 2× "Paeon's Field of Flowers" |
| 20 | Harvesting Data III | MSQ 19 | Harvest >720 min at Hollow Path | 4× Agency Rep, 1× "Paeon's", 1× "Melkarth's" |
| 21 | Squaring the Circle I | MSQ 20, MIN 13 | 2 Scav rolls at Scrap Trees | 2× Agency Rep, 1× Booster Pack |
| 22 | Squaring the Circle II | MSQ 21 | 3 Scav rolls at Centipedes | 2× Agency Reputation |
| 23 | Squaring the Circle III | MSQ 22 | 3 Scav rolls at Blooming Tree | 2× Agency Reputation |
| 24 | Squaring the Circle IV | MSQ 23 | 3 Scav rolls at Airplane Crash | 2× Agency Reputation |
| 25 | Squaring the Circle V | MSQ 24 | 3 Scav rolls at Clearing | 4× Agency Reputation |
| 26 | Squaring the Circle VI | MSQ 25 | 9 Scav rolls at Labs Entrance | 6× Agency Rep, 2× Booster Pack |
| 27 | A Forgotten Friend | MSQ 26 | 5 Scav rolls at Lost Skeleton | 6× Agency Rep, 1× Booster Pack, "KW Maps" Data Chip |
| 28 | Deeper Understanding | MSQ 27 | 2 Scav rolls at Scrap Confluence | 4× Agency Reputation |
| 29 | Computer Blues | MSQ 28 | Buy something in the Marketplace | 2× Agency Reputation |
| 30 | Humility | MSQ 29 | Give 3000 $MUSU, Move to Convenience Store | 4× Agency Rep, 2× Elders Loyalty |
| 31 | Pyramid Power | MSQ 30, MIN 15 | Give Pyramid Engine, Move to Lost Skeleton | 6× Agency Reputation |
| 32 | Safe Hex | MIN 16 | Give 5000 Resin Tincture | 2× Agency Rep, 2× Elders Loyalty, 1× Booster Pack |
| 33 | Holier Than Thou | MSQ 32 | Give 1000 Holy Syrup | 2× Agency Rep, 2× Elders Loyalty |
| 34 | Taking Great Pains | MSQ 33 | Give 1000 Black Poppy Extract | 4× Agency Rep, 4× Elders Loyalty |
| 35 | Steel Your Heart | MSQ 34 | Give 25 Scrap Metal | 4× Agency Rep, 4× Elders Loyalty, 2× Booster Pack, Unlock Caves |
| 36 | The Sanctuary Caves | MSQ 35 | Enter cave zone (Room 15) | 4× Agency Rep, 4× Elders Loyalty, 1× Booster Pack |
| 37 | Into the Depths | MSQ 36 | Harvest >720 min at Temple Cave | 4× Agency Reputation |
| 38 | Feeling in the Dark | MSQ 37 | 7 Scav rolls at Temple Cave | 2× Agency Rep, 2× Elders Loyalty, 1× Booster Pack |
| 39 | Where It Stems From | MSQ 38 | Scavenge 5 Dried Stems | 2× Agency Reputation |
| 40 | Better Than Chopping Wood? | MSQ 39 | Craft 1 Timber | 2× Agency Rep, 2× Elders Loyalty |
| 41 | Throw Me a Bone! | MSQ 40 | Scavenge 5 Bone Chunks | 2× Agency Rep, 1× Booster Pack |
| 42 | Learning From a Master | MSQ 41 | Craft 1 Ashlar | 4× Elders Loyalty |
| 43 | Sound of One Hand Clapping | MSQ 42 | Scavenge 1 Essence of Hearing | 4× Elders Loyalty |
| 44 | Mystery Machines | MSQ 43 | Harvest >720 min at Techno Temple | 4× Elders Loyalty, 1× Unmarked Data Chip |
| 45 | Can't Stop With Just One | MSQ 44 | Move to Lost Skeleton | 2× Agency Rep, 2× Booster Pack |
| 46 | Sweet As Honey | MSQ 45 | Scavenge 5 Honeydew Scale | 2× Agency Rep, 1× Booster Pack |
| 47 | Ringing Any Bells I | MSQ 46 | Harvest >720 min at Cave Crossroads | 4× Elders Loyalty |
| 48 | Pipe Dream | MSQ 47 | Scavenge 5 Patinated Pipes | 2× Agency Rep, 2× Elders Loyalty |
| 49 | Community Service | MSQ 48 | Scavenge 15 Cigarette Butts | 2× Elders Loyalty, 2× Agency Rep, 1× "Melkarth's" |
| 50 | You Smelt It… | MSQ 49 | Craft 1 Ingot | 2× Elders Loyalty |
| 51 | Ringing Any Bells II | MSQ 50 | Give 1 Essence of Hearing | 4× Agency Rep, 4× Elders Loyalty, 2× Booster Pack |
| 52 | Ringing Any Bells III | MSQ 51 | Move to Cave Crossroads, Give 1 Ashlar | 6× Agency Rep, 4× Elders Loyalty |
| 53 | Flash Back | MSQ 52 | Give 1 Flash Talisman | 2× Elders Loyalty, 2× Agency Rep, 2× Booster Pack |
| 54–104 | Caves storyline (continued) | Various | *(see quest CSV for full details)* | Various items, reputation, booster packs |

### Mina's Quests (MIN)

| Index | Title | Prerequisite | Objective | Rewards |
|-------|-------|--------------|-----------|---------|
| 2001 | Grand Opening | MSQ 7 | Enter Mina's Shop (Room 13) | 2× Elders Loyalty |
| 2002 | Customer Loyalty Program | MIN 2001 | Spend 1000 $MUSU at Mina's Shop | 4× Elders Loyalty, 1× "Neith's River of Life" |
| 2003 | Early Market Research I | MIN 2002 | Give 5 Scrap Metal | 2× Elders Loyalty, 1× "Cultivation II" |
| 2004 | Early Market Research II | MIN 2003 | Harvest >720 min at Forest: Insect Node | 2× Elders Loyalty, 2× "Cultivation I" |
| 2005 | Early Market Research III | MIN 2004 | Harvest >720 min on Trash-Strewn Graves | 4× Elders Loyalty, 2× "Neith's River of Life" |
| 2006 | Community Outreach | MIN 2005 | Harvest >720 min at Lost Skeleton (Moonside) | 2× Elders Loyalty, 1× "Cultivation II" |
| 2007 | Restocking | MIN 2006 | Give 5 Plastic Bottle, 5 Pine Cone | 2× Elders Loyalty, 2× "Cultivation III" |
| 2008 | Offering an Apprenticeship | MIN 2003 | Scavenge 1 Pine Cone, 1 Daffodil, 1 Sanguine Shroom, 2 Plastic Bottles | 2× Elders Loyalty |
| 2009 | Basics of Hex — Extracts | MIN 2008 | Craft 500 Pine Pollen | 4× Elders Loyalty |
| 2010 | Basics of Hex — Potions | MIN 2009 | Craft 1 XP Potion | 4× Elders Loyalty |
| 2011 | Hex Education | MIN 2007, MIN 2010 | Craft 1 Bless Potion | 2× Elders Loyalty |
| 2012 | Eye of the White Snake | MIN 2011 | Give 1 Red Amber Crystal | 6× Elders Loyalty |
| 2013 | Memorial for the Forgotten | MIN 2012 | Move to Trash-Strewn Graves, Give 15 Daffodil | 4× Elders Loyalty |
| 2014 | To Whom It May Concern | MIN 2013, MSQ 30 | Give 2 Wooden Sticks, 125 Sanguineous Powder, 125 Resin Tincture | 4× Elders Loyalty |
| 2015 | A Matter of Import | MIN 2014 | Give 9999 $MUSU | 4× Elders Loyalty, 1× Pyramid Engine (Soulbound) |
| 2016 | Misogi | MSQ 31 | Go to Temple by the Waterfall | 4× Elders Loyalty |

### Side Quests (SQ)

| Index | Title | Prerequisite | Objective | Rewards |
|-------|-------|--------------|-----------|---------|
| 3001 | Rejecting Fate | MSQ 3 | Reroll one Kamigotchi | 2× Agency Reputation |
| 3002 | Health & Safety | MSQ 4 | Use item to heal Kami below 100% Health | 2× Agency Rep, 1× "Neith's River of Life" |
| 3003 | There Are Levels to This | MSQ 5 | Level up a Kami | 2× Agency Rep, 1× "Cultivation I" |
| 3004 | Skill Issue | SQ 3003 | Spend a point in any Skill Tree | 2× Agency Reputation |
| 3005 | Spring Rites | Kami liquidated | *(auto-awarded)* | 2× Agency Rep, 1× "Melkarth's Heroic Awakening" |
| 3006 | What's In a Name? | MSQ 8 | Name a Kami | 2× Agency Reputation |
| 3007 | Land Survey | MSQ 17 | Move 500 times | 2× Agency Rep, 2× "Neith's River of Life" |
| 3008 | Peregrination | SQ 3007 | Move 1000 times | 4× Agency Rep, 3× "Neith's River of Life" |
| 3009 | Tips Help The Most Right Now | MIN 2008 | Give 5000 $MUSU | 6× Elders Loyalty |
| 3010 | Hex Education II | MIN 2013 | Craft 1 Grace Potion | 2× Elders Loyalty |
| 3011 | Hex Education III | SQ 3010 | Craft 1 Respec Potion | 2× Elders Loyalty |
| 3012 | Customer Loyalty Program II | MIN 2007 | Spend 15000 $MUSU at Mina's Shop | 6× Elders Loyalty |
| 3013 | Going Out For a Coffee | SQ 3012 | Craft 1 Hostility Potion | 4× Elders Loyalty |
| 3014 | Teatime | SQ 3010 | Give 1 Mint | 6× Elders Loyalty |
| 3015 | The Wages of Sin | Own ≥1 Obol | Give 5 Obols | 2× Agency Rep, 1× Booster Pack |
| 3016 | Go Suck An Egg | SQ 3015 | Give 1 Wonder Egg, Move to Convenience Store | 2× Agency Rep, 2× Elders Loyalty, 1× Booster Pack |
| 3017 | Rearview Mirror | In Room: Treasure Hoard | Harvest >360 min at Treasure Hoard | 4× Agency Reputation |
| 3018 | One Man's Trash | SQ 3017 | Scavenge 25 Otherworld Coins | 4× Agency Rep, 1× "Melkarth's" |
| 3019 | Happy Hunting Ground | In Room: Trophies of the Hunt | 3 Scav rolls at Trophies of the Hunt | 4× Elders Loyalty |
| 3020 | Better to Light a Candle | SQ 3019 | Give 1 Curse Tablet | 4× Elders Loyalty, 5× Booster Pack |
| 3021 | Castle in the Air | In Room: Scenic View | Move to Trophies of the Hunt | 2× Booster Pack |
| 3022 | Sweet Deal | SQ 3021 | Give 3 Rock Candyfloss | 3× "Melkarth's Heroic Awakening" |

> **Total quests:** ~100+ (main story, Mina's, side quests). Some quests have daily repeat variants. Full quest data in `packages/contracts/deployment/world/data/quests/quests.csv`.

---

## Equipment

Equipment items (type `"EQUIPMENT"`) can be equipped to Kamis to provide stat bonuses. Each equipment item has a **slot** defined by its `For` field in the item registry. The slot determines where the item is equipped — you do not choose the slot manually.

### Slot Mapping

| `For` Value | Target | Description |
|-------------|--------|-------------|
| `Kami_Pet_Slot` | Kami | Petpet/accessory slot — all current equipment items use this slot |
| `Passport_slot` | Account | Passport staking slot (for NFT passports) |
| `Account_Badge_Slot` | Account | Account badge slot (reserved for future use) |

### How Equipping Works

1. The system reads the item's `For` field from the registry to determine the slot string.
2. If the slot is already occupied, the existing item is **auto-unequipped** (returned to inventory).
3. The item is consumed from inventory, an equipment instance entity is created, and stat bonuses are applied.
4. Each entity has a **default capacity of 1** equipped item total, expandable via `EQUIP_CAPACITY_SHIFT` bonuses.
5. On unequip, bonuses are cleared (using the `ON_UNEQUIP_{SLOT}` end type) and the item returns to inventory.

### Equipment Items

All current equipment items occupy the `Kami_Pet_Slot`. They are obtained from Booster Packs and lootboxes.

| Index | Name | Rarity | Effect | Description |
|-------|------|--------|--------|-------------|
| 30001 | Mask of Avarice | Common | Power +3 | Theatre mask — boosts Power |
| 30002 | Veil of Avarice | Uncommon | Power +4 | Theatre veil — boosts Power |
| 30003 | Visage of Avarice | Rare | Power +5 | Theatre visage — boosts Power |
| 30004 | Mask of Contempt | Common | Def Type Shift +6% | Ogre mask — boosts defense |
| 30005 | Veil of Contempt | Uncommon | Def Type Shift +8% | Ogre veil — boosts defense |
| 30006 | Visage of Contempt | Rare | Def Type Shift +10% | Ogre visage — boosts defense |
| 30007 | Mask of Mischief | Common | Atk Success Rate +6% | Goblin mask — boosts attack |
| 30008 | Veil of Mischief | Uncommon | Atk Success Rate +8% | Goblin veil — boosts attack |
| 30009 | Visage of Mischief | Rare | Atk Success Rate +10% | Goblin visage — boosts attack |
| 30010 | Old Leafling | Common | Bounty +12% | Petpet — boosts harvest bounty |
| 30011 | Wise Leafling | Uncommon | Bounty +16% | Petpet — boosts harvest bounty |
| 30012 | Elder Leafling | Rare | Bounty +20% | Petpet — boosts harvest bounty |
| 30013 | Old Gumdrop | Common | Rest Max +15% | Petpet — boosts resting recovery |
| 30014 | Wise Gumdrop | Uncommon | Rest Max +20% | Petpet — boosts resting recovery |
| 30015 | Elder Gumdrop | Rare | Rest Max +25% | Petpet — boosts resting recovery |
| 30016 | Old Critter | Common | Health +30 | Petpet — boosts max health |
| 30017 | Wise Critter | Uncommon | Health +40 | Petpet — boosts max health |
| 30018 | Elder Critter | Rare | Health +50 | Petpet — boosts max health |
| 30019 | Crawling Greed | Common | Harvest Fertility +18% | Ladybugs — boost fertility |
| 30020 | Teeming Greed | Uncommon | Harvest Fertility +24% | Ladybugs — boost fertility |
| 30021 | Swarming Greed | Rare | Harvest Fertility +30% | Ladybugs — boost fertility |
| 30022 | Crawling Wrath | Common | Violence +3 | Bees — boost Violence |
| 30023 | Teeming Wrath | Uncommon | Violence +4 | Bees — boost Violence |
| 30024 | Swarming Wrath | Rare | Violence +5 | Bees — boost Violence |
| 30025 | Crawling Cope | Common | Def Success Rate +6% | Worms — boost defense |
| 30026 | Teeming Cope | Uncommon | Def Success Rate +8% | Worms — boost defense |
| 30027 | Swarming Cope | Rare | Def Success Rate +10% | Worms — boost defense |
| 30028 | Antique Tape | Common | Atk Type Shift +6% | Tape — boosts attack |
| 30029 | Heirloom Tape | Uncommon | Atk Type Shift +8% | Tape — boosts attack |
| 30030 | Ancient Tape | Rare | Atk Type Shift +10% | Tape — boosts attack |
| 30031 | Antique Automata | Common | Harvest Intensity +15/hr | Automata — boosts intensity |
| 30032 | Heirloom Automata | Uncommon | Harvest Intensity +20/hr | Automata — boosts intensity |
| 30033 | Ancient Automata | Rare | Harvest Intensity +25/hr | Automata — boosts intensity |
| 30034 | Antique Ledger | Common | Harmony +3 | Ledger — boosts Harmony |
| 30035 | Heirloom Ledger | Uncommon | Harmony +4 | Ledger — boosts Harmony |
| 30036 | Ancient Ledger | Rare | Harmony +5 | Ledger — boosts Harmony |

> Equipment items come in three rarity tiers (Common/Uncommon/Rare) with scaling effects. Each family of items (e.g., Avarice masks, Leaflings) targets a different stat.

---

## Crafting Recipes

Recipes are identified by a `uint32` index. Crafting consumes ingredients from inventory, costs stamina, and produces output items plus XP. Most recipes require a **tool** (Spice Grinder, Portable Burner, or Screwdriver) in inventory.

### Tool Requirements

| Tool | Index | Used For |
|------|-------|----------|
| Spice Grinder | 23100 | Extractions, grinding, and some material crafts |
| Portable Burner | 23101 | Brewing potions, smelting, and some material crafts |
| Screwdriver | 23102 | Chiseling, assembly, and some material crafts |

### Extraction Recipes

| # | Name | Input | Output | Tool | XP | Stamina | Min Lv |
|---|------|-------|--------|------|-----|---------|--------|
| 6 | Extract Pine Pollen | 1× Pine Cone | 500× Pine Pollen | Grinder | 25 | 10 | 1 |
| 7 | Extract Microplastics | 1× Plastic Bottle | 500× Microplastics | Grinder | 100 | 30 | 1 |
| 8 | Extract Daffodil | 1× Daffodil | 500× Essence of Daffodil | Grinder | 25 | 10 | 1 |
| 9 | Extract Mint | 1× Mint | 500× Shredded Mint | Grinder | 100 | 20 | 1 |
| 10 | Extract Black Poppy | 1× Black Poppy | 500× Black Poppy Extract | Grinder | 250 | 20 | 1 |
| 12 | Grind Berry Chalk | 1× Chalkberry | 500× Berry Chalk | Grinder | 50 | 10 | 1 |
| 13 | Crush Red Amber | 1× Red Amber Crystal | 500× Powdered Red Amber | Grinder | 250 | 20 | 1 |
| 16 | Extract Powder | 1× Sanguine Shroom | 500× Sanguineous Powder | Grinder | 25 | 10 | 1 |
| 38 | Extract Microplastics (Cigs) | 1× Cigarette Butt | 250× Microplastics | Grinder | 50 | 15 | 1 |
| 39 | Extract Irradiated Root | 1× Irradiated Root | 500× Pallid Root Extract | Grinder | 250 | 30 | 15 |

### Reagent Recipes

| # | Name | Inputs | Output | Tool | XP | Stamina | Min Lv |
|---|------|--------|--------|------|-----|---------|--------|
| 14 | Mix Holy Syrup | 1× Holy Dust | 500× Holy Syrup | Burner | 100 | 20 | 1 |
| 15 | Process Resin | 1× Resin | 500× Resin Tincture | Burner | 25 | 10 | 1 |

### Material Recipes

| # | Name | Inputs | Output | Tool | XP | Stamina | Min Lv |
|---|------|--------|--------|------|-----|---------|--------|
| 17 | Chisel Cup | 1× Stone | 1× Empty Cup | Screwdriver | 30 | 25 | 1 |
| 31 | Craft Timber (Stems) | 100× Dried Stems | 1× Timber | Burner | 300 | 50 | 15 |
| 34 | Craft Timber (Stick) | 100× Wooden Stick | 1× Timber | Burner | 300 | 50 | 15 |
| 32 | Craft Ingot (Pipes) | 100× Patinated Pipe | 1× Ingot | Burner | 300 | 50 | 15 |
| 35 | Craft Ingot (Scrap) | 100× Scrap Metal | 1× Ingot | Burner | 300 | 50 | 15 |
| 33 | Craft Ashlar (Bone) | 100× Bone Chunk | 1× Ashlar | Grinder | 300 | 50 | 15 |
| 36 | Craft Ashlar (Stone) | 100× Stone | 1× Ashlar | Grinder | 300 | 50 | 15 |

### Potion Recipes

| # | Name | Inputs | Output | Tool | XP | Stamina | Min Lv |
|---|------|--------|--------|------|-----|---------|--------|
| 1 | Brew XP Potion | 1× Plastic Bottle, 250× Pine Pollen | 1× XP Potion | Burner | 50 | 20 | 1 |
| 2 | Brew Greater XP Potion | 1× Glass Jar, 2500× Pine Pollen | 1× Greater XP Potion | Burner | 1000 | 50 | 1 |
| 3 | Brew Respec Potion | 1× Plastic Bottle, 500× Shredded Mint | 1× Respec Potion | Burner | 200 | 50 | 1 |
| 4 | Brew Grace Potion | 1× Plastic Bottle, 100× Essence of Daffodil, 50× Black Poppy Extract | 1× Grace Potion | Burner | 150 | 25 | 1 |
| 5 | Brew Bless Potion | 1× Plastic Bottle, 100× Essence of Daffodil | 1× Bless Potion | Burner | 50 | 15 | 1 |
| 18 | Brew Hostility Potion | 1× Empty Cup, 250× Sanguineous Powder, 250× Pine Pollen | 1× Hostility Potion | Burner | 75 | 20 | 1 |
| 19 | Brew Energy Drink | 1× Scrap Metal, 250× Berry Chalk, 250× Resin Tincture | 1× Energy Drink | Burner | 75 | 20 | 1 |
| 28 | Craft Toadstool Liquor | 5000× Sanguineous Powder, 250× Black Poppy Extract, 250× Berry Chalk | 1× Toadstool Liquor | Burner | 1000 | 50 | 15 |
| 29 | Craft Fortified XP Potion | 1× Greater XP Potion, 300× Powdered Red Amber, 1× Essence of Thought | 1× Fortified XP Potion | Burner | 7500 | 75 | 20 |
| 40 | Craft Pale Potion | 1× Plastic Bottle, 200× Pallid Root Extract, 100× Shredded Mint | 1× Pale Potion | Burner | 500 | 50 | 15 |

### Consumable / Special Recipes

| # | Name | Inputs | Output | Tool | XP | Stamina | Min Lv |
|---|------|--------|--------|------|-----|---------|--------|
| 20 | Write Apology Letter | 2× Wooden Stick, 125× Sanguineous Powder, 125× Resin Tincture | 1× Apology Letter | Grinder | 75 | 20 | 1 |
| 21 | Craft Festival Chime | 3× Scrap Metal, 250× Holy Syrup | 1× Festival Chime | Screwdriver | 100 | 25 | 1 |
| 22 | Craft $MUSU Magnet | 1× Stone, 50× Powdered Red Amber, 100× Holy Syrup | 1× $MUSU Magnet | Screwdriver | 100 | 25 | 1 |
| 23 | Craft Spirit Glue | 1× Plastic Bottle, 200× Microplastics, 200× Berry Chalk | 1× Spirit Glue | Burner | 75 | 20 | 1 |
| 24 | Craft Animistic Poison | 150× Resin Tincture, 5× Blue Pansy, 150× Sanguineous Powder | 1× Animistic Poison | Burner | 200 | 25 | 15 |
| 25 | Craft Cthonic Blight | 100× Holy Syrup, 1× Honeydew Scale, 1× Djed Pillar | 1× Cthonic Blight | Burner | 300 | 25 | 15 |
| 26 | Craft Flash Talisman | 2× Dried Stems, 1× Essence of Touch, 500× Microplastics | 7× Flash Talisman | *(none)* | 1500 | 50 | 20 |
| 37 | Craft Uninteresting Paste | 20× Cigarette Butt, 1× Essence of Taste | 1× Uninteresting Paste | Burner | 1500 | 50 | 15 |

### Essence & Assembly Recipes

| # | Name | Inputs | Output | Tool | XP | Stamina | Min Lv |
|---|------|--------|--------|------|-----|---------|--------|
| 30 | Craft Pure Essence | 1× each of all 6 Essences (Hearing, Touch, Sight, Smell, Taste, Thought) | 1× Pure Essence | *(none)* | 10000 | 75 | 20 |
| 11 | Assemble Aetheric Sextant | 1× Astrolabe Disk, 1× *(key item)*, 1× *(key item)* | 1× Aetheric Sextant | *(none)* | 5000 | 100 | 1 |
| 41 | Assemble Dowsing Rod | 1× Irradiated Root, 1× Ingot, 1× Essence of Sight | 1× Dowsing Rod | *(none)* | 2500 | 100 | 1 |

> **Total recipes:** 41 (including 1 hidden recipe: Craft Wonder Egg from 5 Obols). Some recipes are marked "To Update" or "To Deploy" and may not be live yet. Full recipe data in `packages/contracts/deployment/world/data/crafting/recipes.csv`.

---

## Affinities (Types)

Affinities affect harvest efficacy and liquidation (attack) matchups. There are four affinities:

| Affinity | Description |
|----------|-------------|
| **Normal** | Pure, natural essence — no external influence |
| **Eerie** | Divine or supernatural influence |
| **Insect** | Corruption, defilement, decay |
| **Scrap** | Human-made remnants, material attachments |

### Kami Trait → Affinity Mapping

Each Kami's **body** and **hand** traits carry an affinity. The **face** trait also has an affinity but it is **not used** for harvest efficacy calculations — only body and hand matter for harvesting. Face affinity is used in liquidation (attack) matchups.

> **Source:** Affinities are set per-trait in the trait registry CSV files and stored on-chain in the `AffinityComponent`. The affinity is looked up from the trait's registry entry via `LibKami.getBodyAffinity()` and `LibKami.getHandAffinity()`.

#### Face Traits

| Index | Name | Affinity | Rarity |
|-------|------|----------|--------|
| 0 | .\_.  | Normal | Common |
| 1 | .w. | Normal | Common |
| 2 | n\_n | Normal | Common |
| 3 | >\_> | Scrap | Common |
| 4 | ^-^ | Normal | Common |
| 5 | v\_v | Scrap | Common |
| 6 | o\_O | Normal | Common |
| 7 | O\_o | Normal | Common |
| 8 | -\_- | Normal | Common |
| 9 | x\_x | Insect | Common |
| 10 | o\_o | Normal | Common |
| 11 | O\_0 | Eerie | Common |
| 12 | Teddy | Normal | Rare |
| 13 | Disapproval | Insect | Uncommon |
| 14 | HeartS | Normal | Rare |
| 15 | Impacted | Normal | Rare |
| 16 | Sideeye | Eerie | Uncommon |
| 17 | Lenny 2 | Normal | Rare |
| 18 | :3 | Insect | Uncommon |
| 19 | Unamused | Normal | Uncommon |
| 20 | Ou0 | Eerie | Rare |
| 21 | Concerned | Normal | Uncommon |
| 22 | Lenny 1 | Normal | Legendary |
| 23 | Serious Teddy | Normal | Rare |
| 24 | Drip | Eerie | Epic |
| 25 | Insectoid | Insect | Epic |
| 26 | Insectoid (Partisan) | Insect | Epic |
| 27 | N+B | Scrap | Epic |
| 28 | Sensor | Scrap | Epic |
| 29 | Sated | Eerie | Epic |
| 30 | Hungry | Eerie | Epic |
| 31 | Wassie | *(none)* | Rare |
| 32 | Jiangshi Hat | *(none)* | Epic |
| 33 | Sunglasses | *(none)* | Legendary |
| 34 | Nerd | *(none)* | Epic |
| 35 | Third Eye | *(none)* | Epic |

#### Hand Traits

| Index | Name | Affinity | Rarity |
|-------|------|----------|--------|
| 0 | Candles | Eerie | Epic |
| 1 | Spectral | Eerie | Common |
| 2 | Spinning Coins | Normal | Rare |
| 3 | Coins | Normal | Uncommon |
| 4 | Orbs | Normal | Common |
| 5 | Eyeballs | Eerie | Rare |
| 6 | Fan Blades | Scrap | Epic |
| 7 | Beetle | Insect | Common |
| 8 | Mantis | Insect | Epic |
| 9 | Paws | Normal | Common |
| 10 | Plugs | Scrap | Common |
| 11 | Scorpion | Insect | Common |
| 12 | Tentacles | Eerie | Uncommon |
| 13 | Toasters | Scrap | Uncommon |
| 14 | UFO Catcher | Scrap | Rare |
| 15 | Wrenches | Scrap | Common |
| 16 | Mole Cricket | Insect | Uncommon |
| 17 | Plant | Normal | Uncommon |
| 18 | Guns | Normal | Rare |
| 19 | Torus | Normal | Epic |
| 20 | Crab | Insect | Rare |
| 21 | Melted | Eerie | Common |
| 22 | Wassie Flipper | Normal | Rare |
| 23 | Mudra | Eerie | Legendary |
| 24 | Van de Graaf | Scrap | Legendary |
| 25 | Fairy | Insect | Legendary |
| 26 | Wings | Normal | Legendary |

#### Body Traits

| Index | Name | Affinity | Rarity |
|-------|------|----------|--------|
| 0 | Battery | Scrap | Common |
| 1 | Bee | Insect | Common |
| 2 | Butterfly | Insect | Epic |
| 3 | Caterpillar | Insect | Common |
| 4 | Cube | Normal | Rare |
| 5 | Ghost | Normal | Common |
| 6 | Drip | Eerie | Common |
| 7 | Lightbulb | Scrap | Common |
| 8 | Working CRT Monitor | Scrap | Epic |
| 9 | Broken CRT Monitor | Scrap | Rare |
| 10 | Octahedron | Normal | Epic |
| 11 | Octopus | Eerie | Common |
| 12 | Orb | Normal | Common |
| 13 | Pumpkin | Eerie | Epic |
| 14 | Tube | Normal | Uncommon |
| 15 | Jellyfish | Eerie | Uncommon |
| 16 | Eyes | Eerie | Rare |
| 17 | Amphora | Scrap | Rare |
| 18 | Shrimp | Insect | Uncommon |
| 19 | Spider | Insect | Rare |
| 20 | Plant | Normal | Uncommon |
| 21 | Magatama | Normal | Rare |
| 22 | Snake | Insect | Legendary |
| 23 | Tank | Scrap | Legendary |
| 24 | Hagoromo | Eerie | Legendary |
| 25 | Lotus | Eerie | Rare |
| 26 | Ant | Insect | Rare |
| 27 | Soda Cup | Scrap | Uncommon |
| 28 | Suit | Normal | Legendary |
| 29 | No Kami | Normal | Epic |

### Harvest Affinity Effectiveness

When a Kami harvests at a node, the **body** and **hand** trait affinities are compared against the node's affinity to determine an efficacy modifier. This is calculated in `LibAffinity.getHarvestEffectiveness()`:

| Kami Trait Affinity | Node Affinity | Effectiveness | Effect |
|--------------------|---------------|---------------|--------|
| *(same as node)* | *(any typed)* | **Strong** | Bonus to harvest fertility |
| *(different typed)* | *(different typed)* | **Weak** | Penalty to harvest fertility |
| Normal | *(any)* | **Neutral** | Half of Strong bonus (special case) |
| *(any)* | Normal | **Neutral** | No modifier |
| *(empty)* | *(any)* | **Neutral** | No modifier |

**Key rules:**
- If either the trait affinity or node affinity is empty or `NORMAL`, the result is always **Neutral**
- If both are typed (Eerie/Insect/Scrap) and **match**, the result is **Strong** (bonus)
- If both are typed and **don't match**, the result is **Weak** (penalty)
- `NORMAL` trait affinities receive **half** of the Strong bonus as a special case in `LibHarvest.calcEfficacy()`
- Body affinity has more impact than hand affinity (separate config keys: `KAMI_HARV_EFFICACY_BODY` and `KAMI_HARV_EFFICACY_HAND`)

**Dual-affinity nodes** (e.g., "Eerie-Scrap"): The system picks the most favorable assignment of body/hand to the two node affinities. It prioritizes matching the body trait first since body has higher impact.

### Liquidation (Attack) Affinity Effectiveness

Attack matchups use `LibAffinity.getAttackEffectiveness()` with a rock-paper-scissors triangle:

| Attacker | Defender | Effectiveness |
|----------|----------|---------------|
| Eerie | Scrap | **Strong** |
| Eerie | Insect | **Weak** |
| Scrap | Insect | **Strong** |
| Scrap | Eerie | **Weak** |
| Insect | Eerie | **Strong** |
| Insect | Scrap | **Weak** |
| Normal | Normal | **Special** |
| *(any other combo)* | — | **Neutral** |

> The attack affinity triangle: **Eerie → Scrap → Insect → Eerie**. Normal vs Normal is a special case.

---

## Marketplace (KamiSwap)

Configuration values for the Kami marketplace.

### Contracts

| Contract | Address | Description |
|----------|---------|-------------|
| **WETH** | `0xE1Ff7038eAAAF027031688E1535a055B2Bac2546` | ERC-20 interface for Yominet ETH, used for approval-based flows such as offers and portal deposits |
| **KamiMarketVault** | *(from `KAMI_MARKET_VAULT` config)* | Holds WETH approvals for offer settlement |

### Configuration

| Config Key | Default | Description |
|------------|---------|-------------|
| `KAMI_MARKET_FEE_RATE` | *(admin-set)* | Fee rate as `[precision, numerator]` — fee = `price × numerator / 10^precision` |
| `KAMI_MARKET_FEE_RECIPIENT` | *(admin-set)* | Treasury address that receives marketplace fees |
| `KAMI_MARKET_PURCHASE_COOLDOWN` | `3600` (1 hour) | Cooldown in seconds after a Kami is purchased before it can be relisted |
| `KAMI_MARKET_VAULT` | *(admin-set)* | KamiMarketVault contract address |
| `KAMI_MARKET_ENABLED` | *(admin-set)* | Whether the marketplace is active |

### Currency Usage

| Operation | Currency | Method |
|-----------|----------|--------|
| Buy a listing | ETH (native) | Sent via `msg.value` |
| Make an offer | WETH (ERC-20) | Pre-approved to KamiMarketVault |
| Accept an offer | WETH (ERC-20) | Pulled from buyer by vault |
| KamiSwap listing purchase | ETH (native) | Sent via `msg.value` |

> See [KamiSwap — Marketplace](api/marketplace.md) for full system documentation.

---

## VIP Score System

Kamigotchi integrates with the **Initia VIP** system via `LibVIP` and a standalone `VipScore` contract. VIP scores are tracked per **epoch** (called "stage"), where each stage spans a configurable period (default: 2 weeks). When a player earns VIP-eligible rewards (e.g., harvest bounty), their score is incremented for the current stage. Stages are finalized automatically when the next stage begins. The `VipScore` contract maintains per-address scores per stage, with an allowlist for authorized callers.

---

## Faction Reputation

Factions are named on-chain entities (with metadata: name, description, media URI) that NPCs and potentially players can belong to. Each entity can earn **reputation** with a faction via `LibFaction.incRep()` / `decRep()`. Reputation is stored as a `ScoreEntity` keyed by `(holderID, factionIndex)`, enabling leaderboard queries. Factions are identified by a `uint32` index with entity ID `keccak256("faction", index)`.

---

## GDA Pricing (VRGDA)

`LibGDA` implements a **Variable Rate Gradual Dutch Auction** (discrete VRGDA) pricing model. It calculates the cost of purchasing a quantity of items given a target price, a per-period price decay rate, an emission rate, and the number previously sold. The formula computes a spot price that increases when purchases outpace the target rate and decays when demand is low. This is used for dynamic in-game pricing (e.g., gacha tickets, vendor items). Parameters are configured per auction instance via the `Params` struct (target price, period, decay, rate, quantity).

---

## See Also

- [Entity Discovery](entity-ids.md) — How to derive and discover entity IDs
- [Harvesting](api/harvesting.md) — Harvest mechanics and node interactions
- [Skills & Relationships](api/skills-and-relationships.md) — Skill upgrade system
- [Quests](api/quests.md) — Quest accept/complete mechanics

---

## Trait Affinities

Each Kami has **body** and **hand** traits, each with an affinity (Normal, Eerie, Insect, or Scrap). Matching your Kami's trait affinities to a harvest node's affinity improves efficacy.

### Body Traits

| Index | Name | Affinity | Rarity |
|-------|------|----------|--------|
| 0 | Battery | Scrap | Common |
| 1 | Bee | Insect | Common |
| 2 | Butterfly | Insect | Epic |
| 3 | Caterpillar | Insect | Common |
| 4 | Cube | Normal | Rare |
| 5 | Ghost | Normal | Common |
| 6 | Drip | Eerie | Common |
| 7 | Lightbulb | Scrap | Common |
| 8 | Working CRT Monitor | Scrap | Epic |
| 9 | Broken CRT Monitor | Scrap | Rare |
| 10 | Octahedron | Normal | Epic |
| 11 | Octopus | Eerie | Common |
| 12 | Orb | Normal | Common |
| 13 | Pumpkin | Eerie | Epic |
| 14 | Tube | Normal | Uncommon |
| 15 | Jellyfish | Eerie | Uncommon |
| 16 | Eyes | Eerie | Rare |
| 17 | Amphora | Scrap | Rare |
| 18 | Shrimp | Insect | Uncommon |

### Hand Traits

| Index | Name | Affinity | Rarity |
|-------|------|----------|--------|
| 0 | Candles | Eerie | Epic |
| 1 | Spectral | Eerie | Common |
| 2 | Spinning Coins | Normal | Rare |
| 3 | Coins | Normal | Uncommon |
| 4 | Orbs | Normal | Common |
| 5 | Eyeballs | Eerie | Rare |
| 6 | Fan Blades | Scrap | Epic |
| 7 | Beetle | Insect | Common |
| 8 | Mantis | Insect | Epic |
| 9 | Paws | Normal | Common |
| 10 | Plugs | Scrap | Common |
| 11 | Scorpion | Insect | Common |
| 12 | Tentacles | Eerie | Uncommon |
| 13 | Toasters | Scrap | Uncommon |
| 14 | UFO Catcher | Scrap | Rare |
| 15 | Wrenches | Scrap | Common |
| 16 | Mole Cricket | Insect | Uncommon |
| 17 | Plant | Normal | Uncommon |
| 18 | Guns | Normal | Rare |

### Efficacy

Harvest efficacy depends on body and hand affinity matching the node affinity. The config keys `KAMI_HARV_EFFICACY_BODY` and `KAMI_HARV_EFFICACY_HAND` define multipliers: `base` (neutral), `up` (matching affinity), `down` (mismatched), `special`. Matching both body and hand to the node affinity produces the highest harvest rate.

---

## NPC Merchants

NPCs are located in specific rooms. Use `merchantIndex` when calling `system.listing.buy` or `system.listing.sell`.

| Index | Name | Room | Room Index |
|-------|------|------|------------|
| 1 | Mina | Convenience Store | 13 |
| 2 | Vending Machine | Cave Crossroads | 18 |

### Mina's Listings (Index 1, Room 13)

| Item | Item Index | Currency | Price | Pricing |
|------|-----------|----------|-------|---------|
| Stick | 1001 | Onyx Shards | 0.05 | Fixed |
| Stone | 1002 | Onyx Shards | 1 | Fixed |
| Ribbon | 11001 | MUSU | 100 | GDA 300 Daily 50% Decay |
| Gum | 11301 | MUSU | 60 | GDA 1500 Daily 50% Decay |
| Fruit Candy | 11303 | MUSU | 100 | GDA 750 Daily 50% Decay |
| Cookie Sticks | 11304 | MUSU | 160 | GDA 250 Daily 50% Decay |
| Ice Cream S | 21201 | MUSU | 150 | GDA 60 Daily 50% Decay |
| Ice Cream M | 21202 | MUSU | 250 | GDA 40 Daily 50% Decay |
| Ice Cream L | 21203 | MUSU | 450 | GDA 20 Daily 50% Decay |
| Grinder | 23100 | MUSU | 2500 | Fixed |
| Burner | 23101 | MUSU | 4000 | Fixed |

### Vending Machine Listings (Index 2, Room 18)

| Item | Item Index | Currency | Price | Pricing |
|------|-----------|----------|-------|---------|
| Ribbon | 11001 | MUSU | 100 | GDA 20 Daily 50% Decay |
| Gum | 11301 | MUSU | 60 | GDA 300 Daily 50% Decay |
| Fruit Candy | 11303 | MUSU | 100 | GDA 150 Daily 50% Decay |
| Cookie Sticks | 11304 | MUSU | 160 | GDA 50 Daily 50% Decay |
| Ice Cream S | 21201 | MUSU | 150 | GDA 12 Daily 50% Decay |
| Ice Cream M | 21202 | MUSU | 250 | GDA 8 Daily 50% Decay |
| Ice Cream L | 21203 | MUSU | 450 | GDA 4 Daily 50% Decay |

> **GDA Pricing:** Most merchant items use a Gradual Dutch Auction (GDA). The price starts at the listed value, and supply replenishes daily with 50% decay. Items may be more expensive when recently purchased by other players.
