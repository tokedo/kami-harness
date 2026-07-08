# Day/Night Cycle

Phase-gated timing. Local computation, no RPC needed.

## Cycle Structure

**36-hour cycle** divided into three 12-hour phases:

| Phase | Name | Hours in Cycle | Character |
|---|---|---|---|
| 1 | DAYLIGHT | 0–11 | Standard activity period |
| 2 | EVENFALL | 12–23 | Transition period |
| 3 | MOONSIDE | 24–35 | Night period |

Repeats every 36 hours (129,600 seconds), offset from Unix epoch.

## Calculation

```javascript
function getDayPhase(timestamp = Math.floor(Date.now() / 1000)) {
  const hour = Math.floor(timestamp / 3600) % 36;
  if (hour < 12) return "DAYLIGHT";   // phase 1
  if (hour < 24) return "EVENFALL";   // phase 2
  return "MOONSIDE";                  // phase 3
}
```

### Phase Timing

To calculate when the next phase starts:

```javascript
function getPhaseEnd(timestamp = Math.floor(Date.now() / 1000)) {
  const hour = Math.floor(timestamp / 3600) % 36;
  const currentPhaseEnd = hour < 12 ? 12 : hour < 24 ? 24 : 36;
  const hoursLeft = currentPhaseEnd - hour;
  const secondsIntoHour = timestamp % 3600;
  return (hoursLeft * 3600) - secondsIntoHour; // seconds until next phase
}
```

## What Is Phase-Gated

### Quests

Some quest objectives check the current phase:
- `PHASE` objective type with `BOOLEAN` handler
- Example: "complete during MOONSIDE"
- Must be in the correct phase when completing the quest

### Other Mechanics

The phase system is designed to gate NPC availability, scavenging yields,
or enemy behavior during specific phases. Individual quest objectives specify
their phase requirements.

Phases change automatically over time; no action is required to transition.

## Cross-References

- Phase computation in perception loop: [state-reading.md](state-reading.md)
- Phase-gated quests: [quests.md](quests.md)
- Kill tracking by phase (`LIQ_WHEN_{phase}`): [liquidation.md](liquidation.md)
