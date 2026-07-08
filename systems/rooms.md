# Rooms & Movement

Pathfinding, gates, and movement costs.

## World Structure

**70 rooms** across 4 z-planes (vertical layers).

| Z-Plane | Type | Examples |
|---|---|---|
| z=1 | Overworld | Misty Riverside, Torii Gate, Scrapyard, Forest paths |
| z=2 | Interiors | Convenience Store, Plane Interior, Burning Room |
| z=3 | Underground | Temple Cave, Cave Crossroads, Fungus Garden |
| z=4 | Special | Treasure Hoard, Castle |

### Key Rooms

| Room | Index | Why It Matters |
|---|---|---|
| Misty Riverside | 1 | Starting room for all new accounts |
| Temple by Waterfall | 11 | First Kami naming location |
| Marketplace | 66 | **Trade room** — delivery fee waived for P2P trades |

## Movement Rules

### Adjacency

Two rooms are adjacent if on the **same z-plane** and differ by exactly 1 in
either x or y (no diagonals):

```
isAdjacent = (a.z == b.z) && (
  (a.x == b.x && |a.y - b.y| == 1) ||
  (a.y == b.y && |a.x - b.x| == 1)
)
```

### Special Exits

Rooms can define **special exits** — non-adjacent rooms directly reachable
(portals, tunnels, doors). A room is reachable if adjacent OR listed as a
special exit.

**Z-plane transitions** (e.g., overworld → cave) are **only** possible via
special exits. Rooms on different z-planes are never adjacent.

### Gates (Access Conditions)

Some rooms have **gates** — conditions that must be met to enter:
- Level requirements
- Quest completion flags (e.g., `FLAG_CAVES_UNLOCKED`)
- Item ownership
- Specific source room (gate only applies when coming from that direction)

Gate conditions are checked via `LibConditional` against the account.

## Movement Cost

Each room move costs:

| Resource | Amount |
|---|---|
| Stamina | **5** per move |
| Account XP | **+5** per move |

With 100 max stamina and 60s/point regen, you can make **20 consecutive moves**
from full stamina, then must wait.

System: `system.account.move`
```
executeTyped(uint32 toRoomIndex)
```
- Operator wallet
- Must be adjacent or special exit from current room
- Must pass all gate conditions on destination
- Deducts 5 stamina, grants 5 account XP

## Nodes Within Rooms

Each room can contain **harvest nodes** — sub-locations where Kamis farm.
Currently all ~63 nodes are `HARVEST` type.

Nodes have:
- **Affinity** — affects harvest efficacy (see [harvesting.md](harvesting.md))
- **Level limits** — some nodes restrict max Kami level (e.g., level 15)
- **Scavenge bar** — secondary rewards (see [scavenging.md](scavenging.md))
- **Requirements** — conditions to start harvesting

See [catalogs/nodes.csv](../catalogs/nodes.csv) for all nodes.

## Pathfinding

Room-dependent mechanics:

- Many quests require being in a specific room (`ROOM` objective).
- Room 66 (Marketplace) waives P2P trade delivery fees.
- NPC transactions require being in the same room as the NPC, unless the NPC's
  room = 0 (globally accessible).

### Path Computation

1. Check current room (from account state)
2. Look up target room coordinates
3. Calculate path via adjacency + special exits
4. Estimate stamina cost: 5 * number of moves
5. Check gate conditions along the path

### Stamina Management

```
maxStamina = 100
regenRate = 1 point per 60 seconds
moveCost = 5 per room
```

Time to regen from 0 to full: 100 minutes.
Moves from full stamina: 20.

## Room Data

See [catalogs/rooms.csv](../catalogs/rooms.csv) for all rooms:
- Coordinates (x, y, z)
- Exit connections
- Gate conditions
- Names

## Cross-References

- Harvest node selection: [harvesting.md](harvesting.md)
- Node catalog: [catalogs/nodes.csv](../catalogs/nodes.csv)
- Stamina system: [accounts.md](accounts.md)
- Quest room requirements: [quests.md](quests.md)
- Trade room (66) benefits: [trading.md](trading.md)
