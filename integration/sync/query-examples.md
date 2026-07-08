# Query Examples — Synced World State

Two query methods, depending on needs:

| Method | Suited to |
|---|---|
| **Direct SQL** (PostgreSQL) | Aggregate queries, joins, filtering, ad-hoc exploration |
| **REST API** (`/api/logs`) | Programmatic access from agent code, table-specific log fetching |

## Direct SQL (PostgreSQL)

Connect to the synced database:

```bash
# Via docker compose
docker compose exec postgres psql -U kamigotchi -d kamigotchi

# Or directly
psql "postgres://kamigotchi:kamigotchi@localhost:5432/kamigotchi"
```

The postgres-decoded indexer creates a schema named after the World
contract address. Set the search path first:

```sql
SET search_path TO "0x2729174c265dbBd8416C6449E0E813E88f43D0E7";
```

### Discover available tables

```sql
-- List all synced MUD tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = '0x2729174c265dbBd8416C6449E0E813E88f43D0E7'
ORDER BY table_name;
```

> **Important:** The exact table and column names depend on how
> Kamigotchi's MUD Store tables are defined. Run the discovery query
> above first, then `\d <table_name>` to inspect columns. The examples
> below use likely naming patterns — adjust to match actual schema.

### Agent-relevant queries

**Get all my Kamis and their current state:**
```sql
-- Replace <account_id> with the account's entity ID (uint256)
SELECT k.*
FROM <kami_table> k
WHERE k.owner_id = '<account_id>';
```

**Who is harvesting on node 14?**
```sql
SELECT h.*
FROM <harvest_table> h
WHERE h.node_index = 14
  AND h.active = true;
```

**What is Kami X's last synced HP?**
```sql
SELECT health_base, health_shift, health_boost, health_sync
FROM <kami_stats_table>
WHERE entity_id = '<kami_id>';

-- Compute effective max HP:
-- max_hp = floor((1000 + health_boost) * (health_base + health_shift) / 1000)
-- Last synced actual HP = health_sync
```

**List all accounts in room 66:**
```sql
SELECT *
FROM <account_table>
WHERE room = 66;
```

**Get all active harvest entities with nodes and start times:**
```sql
SELECT h.entity_id, h.kami_id, h.node_index, h.start_time
FROM <harvest_table> h
WHERE h.active = true
ORDER BY h.node_index, h.start_time;
```

**Inventory check — Musu and Onyx across accounts:**
```sql
SELECT owner_id, item_index, value
FROM <inventory_table>
WHERE item_index IN (1, 100)  -- 1=Musu, 100=Onyx Shards
ORDER BY owner_id, item_index;
```

**Node occupancy counts (for harvest node selection):**
```sql
SELECT node_index, COUNT(*) as harvesters
FROM <harvest_table>
WHERE active = true
GROUP BY node_index
ORDER BY harvesters DESC;
```

## REST API

The indexer serves a REST API on port 3001.

### Get all logs for the World contract

```bash
# Fetch all table logs (no filter)
curl "http://localhost:3001/api/logs?input=$(python3 -c "
import urllib.parse, json
print(urllib.parse.quote(json.dumps({
  'chainId': 428962654539583,
  'address': '0x2729174c265dbBd8416C6449E0E813E88f43D0E7',
  'filters': []
})))
")"
```

### Filter by table ID

```bash
# Fetch logs for a specific MUD table
curl "http://localhost:3001/api/logs?input=$(python3 -c "
import urllib.parse, json
print(urllib.parse.quote(json.dumps({
  'chainId': 428962654539583,
  'address': '0x2729174c265dbBd8416C6449E0E813E88f43D0E7',
  'filters': [{'tableId': '0x<table_id_hex>'}]
})))
")"
```

Response format:
```json
{
  "blockNumber": "123456",
  "logs": [
    {
      "address": "0x2729...",
      "tableId": "0x...",
      "keyTuple": ["0x..."],
      "staticData": "0x...",
      "encodedLengths": "0x...",
      "dynamicData": "0x..."
    }
  ]
}
```

### From agent code (JavaScript)

```javascript
import { createIndexerClient } from "@latticexyz/store-sync/indexer-client";

const indexer = createIndexerClient({ url: "http://localhost:3001" });

const result = await indexer.getLogs({
  chainId: 428962654539583,
  address: "0x2729174c265dbBd8416C6449E0E813E88f43D0E7",
  filters: [],
});

console.log(`Synced to block ${result.blockNumber}, ${result.logs.length} logs`);
```

### Other endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Readiness check |
| `/` | GET | Basic hello/version |
| `/metrics` | GET | Prometheus metrics |

## How This Relates to state-reading.md

The sync replaces the need for most individual RPC calls documented in
[systems/state-reading.md](../../systems/state-reading.md):

| state-reading.md pattern | Sync equivalent |
|---|---|
| `getter.getKami(id)` | SQL query on Kami table |
| `getter.getAccount(id)` | SQL query on account table |
| `ownsKami.getEntitiesWithValue(accountId)` | SQL `WHERE owner_id = ?` |
| "Who else is on my node?" (hard via RPC) | SQL `WHERE node_index = ? AND active` |
| Inventory enumeration (loop over entities) | SQL `WHERE owner_id = ?` |

**Still need state-reading.md for:**
- HP/stamina/bounty projection formulas (sync gives snapshots, not live values)
- GDA price projection (local computation on synced base prices)
- Quest completability checks (`staticCall` pattern)
- Kamiden indexer data (marketplace listings, kill feed, activity stream)
