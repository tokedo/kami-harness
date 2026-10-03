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
    A new account can start owner-only: the `create_operator_wallet`
    tool generates the operator keypair inside the server process.
  - The server reads both keys but **never exposes them to the connected
    client**.
- **Yominet RPC**: the default
  (`https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`) works out
  of the box. Override via the `RPC_URL` env var.
- **Ethereum mainnet RPC**: required, no default. The bridge tools
  (`bridge_eth_from_mainnet`, `bridge_status`) quote and sign mainnet
  transactions through the `MAINNET_RPC_URL` endpoint; it is part of the
  environment definition and is recorded in run manifests, and the
  server fails at startup when it is unset.
- **kami-lens**: world-state reads (27 of the 34 PERCEIVE tools) are
  answered by a **local** [kami-lens](https://github.com/tokedo/kami-lens)
  daemon that you run yourself — there is no hosted read service. It is
  a Node.js daemon and ships a Docker Compose sample; you need one of
  Node.js 20+ or Docker. Set it up in step 7. Without it, those tools
  raise `LensUnavailableError` and the rest of the surface is
  unaffected.

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
# Edit ~/.blocklife-keys/.env: fill in MAIN_OPERATOR_KEY, MAIN_OWNER_KEY,
# and MAINNET_RPC_URL (required — the server refuses to start without it)
# Add more accounts as needed: FARM1_OPERATOR_KEY=, FARM1_OWNER_KEY=
```

### Where the nonce ledger lives

Every send records what it signed in a small per-wallet ledger so that a
restarted server never reuses a nonce under a transaction it already
broadcast. It lives in its own state directory, independent of where
keys come from (keys file, Keychain or plain environment) and never
holding key material:

- `KAMI_LANE_DIR` if set, else `$XDG_STATE_HOME/kami-harness/lanes` if
  `XDG_STATE_HOME` is set, else `~/.kami-harness/lanes`;
- directory mode 0700, one JSON file per (chain, wallet address), mode
  0600, written atomically.

On a filesystem that does not survive a restart (a container without a
volume) the ledger starts empty after every restart: nonces fall back to
the node's own `pending` count, and transactions the previous process
left in flight are invisible to the new one — a nonce one of them later
consumes is reported as taken by a transaction "not signed by this
harness", and a tail it left armed behind a gap is not drained until a
later send reaches it. Mount the directory on a volume to keep those
guarantees.

### The call time box

Every served call fits a wall-clock box, `KAMI_CALL_BUDGET_S` seconds
(default 90) — a server setting, read at startup, not a tool parameter.
A loop tool whose box is spent stops at a step boundary and
returns what it did, with `time_boxed: true` and `remaining` (what was
not attempted). The value is stated in the initialize `instructions`.

## 5. Configure the public roster (in the repo)

```bash
cp accounts/roster.yaml.template accounts/roster.yaml
# Edit accounts/roster.yaml: fill in the matching public addresses
# for each label (must match the LABEL prefixes in .env).
```

The server cross-checks `~/.blocklife-keys/.env` against
`accounts/roster.yaml` on startup and warns on mismatches (on stderr —
stdout is the JSON-RPC transport and carries protocol only).

### Where secrets actually come from

Every key, API credential and token is resolved through
[`executor/secrets_store.py`](executor/secrets_store.py), which has two
backends. **You do not have to configure any of this**: the default is
the keys file you just created, which is what every earlier version did.

| backend | what it uses |
|---|---|
| `envfile` (default) | `~/.blocklife-keys/.env`, or `KAMI_KEYS_FILE` |
| `keychain` | the macOS login Keychain — generic-password items `kami-mcp/<NAME>`, account = your login user — for the names a manifest marks protected; everything else still comes from the keys file |

The manifest is a **names-only** file (one variable name per line, no
values) sitting beside the keys file: the keys file's name with a
trailing `.env` removed, plus `.secrets.names`. So
`~/.blocklife-keys/.env` looks for `~/.blocklife-keys/.secrets.names`.
**If it does not exist, nothing is protected and no Keychain call is
ever made.** Set `KAMI_SECRETS_BACKEND=keychain` and write that manifest
to move the named keys into the Keychain; `ALLOW_ENV_SECRETS=1` is the
escape hatch that lets a protected name fall back to the keys file, with
a warning.

Under either backend, secret values are held in the server process only:
they are never exported to the process environment (so no child process
inherits them), never returned by a tool, and never printed. Names and
locations are — an error tells you *which* variable is missing and
*where* it should be, never what it holds. `env.template` documents
every switch.

## 6. (Optional) Enable secret-file guardrails

If your client supports pre-tool hooks (e.g. Claude Code), install deny
rules and a `PreToolUse` hook that block any tool call attempting to read
`.env`, `*.key`, `*.pem`, or paths under `~/.blocklife-keys/`:

```bash
cp .claude/settings.json.template .claude/settings.json
```

The keys are only ever needed by the server process, which loads them
outside the client's tool surface.

## 7. Install and run kami-lens (required for world-state reads)

27 of the 34 PERCEIVE tools are thin wrappers over a **local**
kami-lens daemon — one socket request each, passed straight back to the
caller. The other 7 read the chain directly (or, for
`get_expected_objective`, the local quest catalog). Until the daemon
is running, the 27 raise
`LensUnavailableError` — they never fall back to a hosted service and
never return an empty result in its place. ACT and META
tools do not depend on it.

This server version is built against kami-lens release **1.0.0**,
commit `0ffc8a7`, as declared in [`SPEC.md`](SPEC.md) D1. Several 4.0.0 parameters
(`at_least_block`, `equipment`, the node and feed selectors) and two
tools (`lens_receipts`, `lens_pool_history`) need 1.0.0: an older daemon
refuses them with an error, so upgrade the daemon first. kami-lens is
not published to npm or a container registry, so build it from the
repository:

```bash
git clone https://github.com/tokedo/kami-lens
cd kami-lens
git checkout 0ffc8a7        # kami-lens 1.0.0, the pin this server version is built against
npm install && npm run build
node dist/cli.js daemon      # long-running: sync daemon + query socket
```

Or run it with the committed Compose sample
([`docker-compose.sample.yml`](https://github.com/tokedo/kami-lens/blob/main/docker-compose.sample.yml)),
which needs no configuration — the baked Yominet defaults reach a live
mirror on their own:

```bash
cp docker-compose.sample.yml docker-compose.yml
docker compose up -d
```

Cold start pulls a state snapshot and then follows the chain; give it a
minute before expecting complete answers.

### Point the server at the socket

The server sends one newline-delimited JSON request per connection over
an AF_UNIX socket at `<data dir>/kami-lens.sock` (the daemon answers a
connection's requests in order, so a read held by `at_least_block` must
not share one — none does). The server looks for it at the daemon's own
platform default:

| Platform | Default socket path |
|---|---|
| macOS | `~/Library/Application Support/kami-lens/kami-lens.sock` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/kami-lens/kami-lens.sock` |
| Windows | `%LOCALAPPDATA%\kami-lens\kami-lens.sock` |

A daemon started with the defaults needs no configuration here. Keep
the lens data directory's path short: an AF_UNIX socket path is capped
by the OS (103 bytes on macOS, 107 on Linux), the daemon refuses a
longer one with `SOCKET_PATH_TOO_LONG`, and this server reports the same
cause as `LensUnavailableError: socket error: AF_UNIX path too long`. If
you moved its data directory (`--data-dir`) or run it in Docker — where the
socket lives on the container's `/data` volume and must be bind-mounted
out to the host — set the path explicitly in
`~/.blocklife-keys/.env` (keys documented in
[`env.template`](env.template)):

```bash
KAMI_LENS_SOCKET=/absolute/path/to/kami-lens.sock

# Optional, same file:
# PRESENTATION_MODE=envelope   # or name-free (daemon withholds
#                              # player-authored names, with receipt)
# KAMI_CHAT_ENABLED=false      # lens_chat/chat_send answer
#                              # CHAT_DISABLED while off
# KAMI_ERROR_SNIPPETS=false    # append a "[mechanics]" block to error
#                              # results: the state read, the tools whose
#                              # state gate accepts it, what the attempted
#                              # tool requires, the gas ceiling used.
#                              # Error text only — the tool surface
#                              # (count, descriptions, tools_hash) is
#                              # identical either way.
```

Verify the daemon before moving on — it exits 0 only when the daemon is
LIVE:

```bash
node dist/cli.js health     # or: docker compose exec kami-lens kami-lens health
```

Once the MCP server is connected (step 8), `lens_status()` reports the
same thing through the tool surface: sync state, live block, stream
health, and the daemon's own version.

## 8. Register the MCP server with your client

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

## 9. Smoke-test the server

```bash
cd executor
python3 -m pytest tests/ -v
```

The suite runs against committed catalog and quest-state fixtures — expect
all tests to pass without a live account, and without the kami-lens
daemon running (lens behavior is covered by fixtures). Import errors here
mean the Python environment from step 3 isn't set up correctly.

## 10. Seed the trade order-book cache (one-time)

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

## 11. Bootstrap an account (from a connected client)

With the server connected, initialize an account by calling:

```
list_accounts()                       # META: see what's configured
lens_status()                         # PERCEIVE: daemon LIVE + synced?
lens_account(account_key="main")      # PERCEIVE: identity, room, stamina, roster
lens_party(account_index=<index>)     # PERCEIVE: your kamis with full vitals
```

If `lens_status()` errors instead of answering, the daemon from step 7
is not reachable — no other read will work until it is.

After that, every other tool is available. An account that exists only
as an owner key (no operator, no on-chain registration, funds still on
Ethereum mainnet) is brought to a playable state through the tool
surface itself — see the Onboarding and Bridging sections of
[`executor/README.md`](executor/README.md), which also has the full
tool reference.

---

## Troubleshooting

### `Account 'main' not found. Available: ...`
The server scanned the secret store for `*_OPERATOR_KEY` /
`*_OWNER_KEY` pairs. The label you passed (e.g. `main`) didn't match.
Check that `MAIN_OPERATOR_KEY=…` (uppercased) is set in
`~/.blocklife-keys/.env` — or, on the `keychain` backend, that
`security find-generic-password -s kami-mcp/MAIN_OPERATOR_KEY` finds it.
The startup report on stderr names every secret it resolved and where
each one came from.

### PERCEIVE reads fail with `LensUnavailableError`
The kami-lens daemon from step 7 is not running, or the server is
looking at the wrong socket. Confirm the daemon is LIVE
(`node dist/cli.js health`, exit 0), then check that the socket it
created matches what the server expects — the platform default in the
table above, or whatever `KAMI_LENS_SOCKET` is set to in
`~/.blocklife-keys/.env`. A daemon in Docker needs its `/data` socket
bind-mounted to a host path and `KAMI_LENS_SOCKET` pointed there. An
error reading `AF_UNIX path too long` means the socket path itself is
over the OS limit: move the lens data directory to a shorter path.

### A lens read answers, but `meta.stale` is `true`
The daemon is degraded or still catching up and is serving from
last-synced state. This is reported, not hidden: the flag reaches you
untouched. `lens_status()` says why. A cold start needs a minute.

### Tests fail with `no row in catalogs/quests/quests.csv`
The quest catalogs are committed in `catalogs/quests/`. If they're
missing, you have an incomplete clone — `git pull` to refresh.

### A large harvest batch is refused before it is sent
`harvest_start`, `harvest_stop`, and `harvest_collect` take at most
**10 kamis per call**. Yominet caps a single transaction's gas limit at
**31,500,000** (its per-transaction lane cap, below the 45,000,000 block
limit), and that lane alone would admit 31 / 15 / 17 kamis at the
harness's per-kami gas provision; but in play a start of 22–28 kamis
and a stop of 12-15 (12 on high-level kamis) failed the RPC node's own
dry-run, while 10 landed for both. The cap is that measured admission, enforced before signing. A
larger list is refused pre-send, naming the number that fits; split at
the call site. The harness never splits for you: one tool call is one
transaction, because an agent's plan/act accounting depends on it. When
a multi-kami batch's dry-run fails, it is re-run kami by kami, and the
error says whether the batch SIZE or one kami (ITEM) failed.

---

## Next steps

- [`README.md`](README.md) — the environment interface specification:
  tool surface, world-knowledge docs, and world model.
- [`executor/README.md`](executor/README.md) — the full MCP tool
  reference (100 tools, by class).
- [`integration/system-ids.md`](integration/system-ids.md) and
  [`integration/entity-ids.md`](integration/entity-ids.md) — if you want
  to extend the interface with new tools.
