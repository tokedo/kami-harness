# Setup — Kamigotchi Environment Interface

This walks through standing up the **environment interface**: configuring
wallets and RPC, running the MCP server, and connecting a client. The
interface is a stdio MCP server (`executor/server.py`) that exposes
Kamigotchi perception and action as tools; any MCP client can drive it.

> This repo contains no agent policy. It is the environment a KamiBench
> agent connects to, not the agent. For the reference agent scaffold, see
> the `kami-agent` repo.

---

## 1. Prerequisites

- **Python 3.11+** and `pip`.
- An **MCP client**. [Claude Code](https://docs.claude.com/en/docs/claude-code/quickstart)
  is one option; any MCP-capable client works.
- **Two on-chain wallets per account you'll play**:
  - **Owner** — registers the account, holds ETH and tokens, mints,
    trades, approves ERC-20s.
  - **Operator** — signs all gameplay transactions (harvest, move, equip,
    quests). Delegated from owner via `system.account.set.operator`.
  - The server reads both keys but **never exposes them to the connected
    client**.
- **Yominet RPC**: the default
  (`https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`) works out
  of the box. Override via the `RPC_URL` env var.
- **Kamibots account**: the server uses Kamibots' Playwright API for state
  reads and strategy execution. The first session calls
  `register_kamibots(account=...)`, which signs with the owner key and
  provisions an API key automatically.

## 2. Clone the repo

```bash
git clone https://github.com/<you>/kami-harness
cd kami-harness
```

Cloning your own fork lets you keep `accounts/roster.yaml` and local
config private while still pulling interface updates from upstream.

## 3. Install server dependencies

```bash
cd executor
pip install -r requirements.txt
cd ..
```

## 4. Set up keys (OUTSIDE the repo)

Private keys live at `~/.blocklife-keys/.env`, **outside the project
directory**. Some MCP clients auto-index the working directory; keeping
keys external means there is nothing sensitive in the tree to read.

```bash
mkdir -p ~/.blocklife-keys
cp env.template ~/.blocklife-keys/.env
chmod 600 ~/.blocklife-keys/.env
# Edit ~/.blocklife-keys/.env: fill in MAIN_OPERATOR_KEY, MAIN_OWNER_KEY
# Add more accounts as needed: FARM1_OPERATOR_KEY=, FARM1_OWNER_KEY=
```

## 5. Configure the public roster (in the repo)

```bash
cp accounts/roster.yaml.template accounts/roster.yaml
# Edit accounts/roster.yaml: fill in the matching public addresses
# for each label (must match the LABEL prefixes in .env).
```

The server cross-checks `~/.blocklife-keys/.env` against
`accounts/roster.yaml` on startup and warns on mismatches.

## 6. (Optional) Enable secret-file guardrails

If your client supports pre-tool hooks (e.g. Claude Code), install deny
rules and a `PreToolUse` hook that block any tool call attempting to read
`.env`, `*.key`, `*.pem`, or paths under `~/.blocklife-keys/`:

```bash
cp .claude/settings.json.template .claude/settings.json
```

The keys are only ever needed by the server process, which loads them
outside the client's tool surface.

## 7. Register the MCP server with your client

Point your client at the executor. For Claude Code, add it at the project
level (`./.mcp.json`, committed) or user-global:

```json
{
  "mcpServers": {
    "kamigotchi": {
      "command": "python",
      "args": ["executor/server.py"],
      "cwd": "/absolute/path/to/kami-harness"
    }
  }
}
```

The server runs as a stdio MCP server. On connect it reports its
`server_version` (the interface `SCHEMA_VERSION`; see
[`CHANGELOG.md`](CHANGELOG.md)) in the initialize handshake.

## 8. Smoke-test the server

```bash
cd executor
python3 -m pytest tests/ -v
```

The suite runs against committed catalog and quest-state fixtures — expect
all tests to pass without a live account. Import errors here mean the
Python environment from step 3 isn't set up correctly.

## 9. Seed the trade order-book cache (one-time)

`get_item_orderbook` discovers trade entities from World event logs, but
the public Yominet RPC is a pruned node (~1M blocks of history): trades
created before the prune horizon are invisible to a log scan. Seed the
trade-ID cache once from the Kamigaze state snapshot:

```bash
cd executor
python3 kwob_bootstrap.py   # writes executor/.cache/kwob_trades.json
cd ..
```

Staleness behavior after the one-time bootstrap:

- Every `get_item_orderbook` call scans new logs incrementally and
  rewrites the cache file, so any call within the prune window (~1M
  blocks) keeps coverage complete indefinitely — no re-runs needed in
  normal operation.
- If the server goes longer than the prune window without an order-book
  call, or the cache file is lost, the missing range can no longer be
  recovered from logs. `get_item_orderbook` then raises an error naming
  `executor/kwob_bootstrap.py` instead of silently returning an
  incomplete book — re-run the bootstrap to recover.
- The cache file is generated state and is gitignored. For autonomous
  deployments, treat the bootstrap as a provisioning step: run it once
  per host as part of deployment.

## 10. Bootstrap an account (from a connected client)

With the server connected, initialize an account by calling:

```
list_accounts()                       # see what's configured
register_kamibots(account="main")     # owner-signed, provisions API key
store_operator_key(account="main")    # encrypted at rest on Kamibots
get_tier(account="main")              # confirms API access
get_account_kamis(account="main")     # discover your kamis
```

After that, every other tool is available. See
[`executor/README.md`](executor/README.md) for the full tool reference.

---

## Troubleshooting

### `Account 'main' not found. Available: ...`
The server scanned `~/.blocklife-keys/.env` for `*_OPERATOR_KEY` /
`*_OWNER_KEY` pairs. The label you passed (e.g. `main`) didn't match.
Check that `MAIN_OPERATOR_KEY=…` (uppercased) is set in
`~/.blocklife-keys/.env`.

### Tests fail with `no row in catalogs/quests/quests.csv`
The quest catalogs are committed in `catalogs/quests/`. If they're
missing, you have an incomplete clone — `git pull` to refresh.

### `register_kamibots` fails with a signature error
The owner key in `.env` doesn't match the owner address in
`roster.yaml`, or the owner address isn't the on-chain owner of the
operator. Recheck both.

### A large `harvest_start` batch runs out of gas
Default gas limits assume a 20-kami batch fits in Yominet's lane gas
limit. For >20 kamis, split into smaller batches at the call site.
`harvest_start`'s gas limit is 3M (raised from 1.5M after observed
out-of-gas on node-change waves).

---

## Next steps

- [`README.md`](README.md) — the environment interface specification:
  tool surface, world-knowledge docs, and world model.
- [`executor/README.md`](executor/README.md) — the full MCP tool
  reference (78 tools).
- [`integration/system-ids.md`](integration/system-ids.md) and
  [`integration/entity-ids.md`](integration/entity-ids.md) — if you want
  to extend the interface with new tools.
