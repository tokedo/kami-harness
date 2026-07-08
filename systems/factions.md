# Factions & Reputation

Reputation sources, tracking, and how to read reputation.

## Factions

| Index | Name | Key | Description |
|---|---|---|---|
| 1 | The Agency | Agency | Relationship with the world administrators (the Menu) |
| 2 | The Elders | Mina | Relationship with Mina and her business/investors |
| 3 | The Nursery | Nursery | Relationship with the Nursery and its mysterious forces |

## Reputation Sources

Reputation is gained primarily through **quest rewards**:

| Faction | Quest Type | Rep per Quest |
|---|---|---|
| Agency | Main story quests (MENU) | 2, 4, or 6 |
| Elders (Mina) | Mina's faction quests (2001–2016) | 2, 4, or 6 |
| Nursery | Specific quests | 4 |

Reputation values vary per quest; exact amounts are in quest reward data.

Agency reputation accrues from main story quest progression. Mina (Elders)
faction quests (2001–2016) unlock after meeting their main quest
prerequisites. Nursery reputation comes from specific quest rewards.

## Reputation Tracking

Reputation is tracked as a **leaderboard score** per account per faction:

```
reputationId = keccak256("faction.reputation", accountId, factionIndex)
```

Reputation can be read via the score system's `Value` component.

### Quest-Gated Content

Some quests or goals may gate on reputation thresholds; no specific values
are currently known.

## NPC Faction Assignment

NPCs belong to factions (tracked via `IndexFaction` component). This
determines which faction each NPC's quests serve.

## How to Read Reputation

```javascript
const repId = BigInt(ethers.keccak256(ethers.solidityPacked(
  ["string", "uint256", "uint32"],
  ["faction.reputation", accountId, factionIndex]
)));
const repValue = await valueComp.getValue(repId);
```

## Cross-References

- Faction quests: [quests.md](quests.md)
- Main quest chain (Agency rep source): [quests.md](quests.md)
