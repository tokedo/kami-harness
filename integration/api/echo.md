> **Doc Class:** Core Resource
> **Canonical Source:** Kamigotchi on-chain contracts on Yominet and the official repository (`Asphodel-OS/kamigotchi-open`, the public mirror of the studio's development repo).
> **Freshness Rule:** Verify mutable values against canonical sources before merge.

# Echo

Echo functions force the game to re-emit entity data. Use these when the off-chain indexer is lagging and your client has stale state.

---

## kamis()

Force-emit the calling account's Kami data.

| Property | Value |
|----------|-------|
| **System ID** | `system.echo.kamis` |
| **Wallet** | 🎮 Operator |
| **Parameters** | None |
| **Gas** | Default |

### Description

Triggers the World to re-emit all Kami entity data associated with the caller's account. The indexer will pick up these events and update client state. Useful when the UI shows outdated stats after a level-up or equipment change.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ECHO_KAMIS_ABI = ["function executeTyped() returns (bytes)"];
const echoKamis = await getSystem(
  "system.echo.kamis",
  ECHO_KAMIS_ABI,
  operatorSigner
);

const tx = await echoKamis.executeTyped();
await tx.wait();
console.log("Kami data re-emitted");
```

### When to Use

- Client UI shows stale Kami stats after a level-up
- After equipping/unequipping items, stats don't update
- Debugging indexer sync issues

---

## room()

Force-emit the calling account's Room data.

| Property | Value |
|----------|-------|
| **System ID** | `system.echo.room` |
| **Wallet** | 🎮 Operator |
| **Parameters** | None |
| **Gas** | Default |

### Description

Triggers the World to re-emit Room data for the caller's current room. Includes room occupants, objects, and state. Use when the UI doesn't reflect your current room after a `move()`.

### Code Example

```javascript
import { getSystem, ownerSigner, operatorSigner } from "./kamigotchi.js";

const ECHO_ROOM_ABI = ["function executeTyped() returns (bytes)"];
const echoRoom = await getSystem(
  "system.echo.room",
  ECHO_ROOM_ABI,
  operatorSigner
);

const tx = await echoRoom.executeTyped();
await tx.wait();
console.log("Room data re-emitted");
```

### When to Use

- After `move()`, the room state doesn't update
- Other players' presence doesn't show up
- Room items or harvest nodes appear missing

---

## Related Pages

- [Account — move()](account.md#move) — Moving between rooms
- [Kami](kami.md) — Kami stat management
- [Player API Overview](../sdk-setup.md) — Setup and calling conventions
