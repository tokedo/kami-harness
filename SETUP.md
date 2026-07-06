# Setup — Kamigotchi Agent Harness

This is the public starter for AI agents that play Kamigotchi (a pure
on-chain MMORPG on Yominet). Pick one of two operating modes:

| Mode | Best for | Loop |
|---|---|---|
| **A. Hybrid** | Testing, iteration, supervised play, learning the harness | Interactive Claude Code session on your laptop. You give direction, the agent executes via MCP tools, you review. |
| **B. Fully autonomous** | 24/7 quest grinds, long unattended runs | Claude Code runs headless on a small VM, triggered by cron. Agent reads its own plan, perceives, acts, commits + pushes. No human in the loop during the session. |

Both modes share the same harness — only the runtime wrapper differs.
Set up the common pieces first, then pick A or B.

---

## Common setup (both modes)

### 1. Prerequisites

- **Python 3.11+** and `pip`
- **Claude Code CLI** ([install instructions](https://docs.claude.com/en/docs/claude-code/quickstart)).
  Authenticate with your Anthropic account (Max subscription recommended for
  autonomous mode — the cron schedule benefits from a generous quota).
- **Two on-chain wallets per account you'll play**:
  - **Owner** — registers the account, holds ETH and tokens, mints, trades, approves ERC-20s.
  - **Operator** — signs all gameplay transactions (harvest, move, equip, quests). Delegated from owner via `system.account.set.operator`.
  - The agent's MCP server reads both keys but **never exposes them to the LLM context**.
- **Yominet RPC**: the default (`https://jsonrpc-yominet-1.anvil.asia-southeast.initia.xyz`) works out of the box. Override via `RPC_URL` env var if you need to.
- **Kamibots account**: the harness uses Kamibots' Playwright API for state reads and strategy execution. The first session calls `register_kamibots(account=...)`, which signs with the owner key and provisions an API key automatically.

### 2. Clone this repo (as a private fork)

```bash
git clone https://github.com/<you>/kami-harness
cd kami-harness
```

Forking lets you commit your own `memory/`, custom `strategies/`, and
`accounts/roster.yaml` without exposing them publicly. You'll still
pull harness updates from this upstream.

### 3. Install Python deps

```bash
cd executor
pip install -r requirements.txt
cd ..
```

### 4. Set up keys (OUTSIDE the repo)

Private keys live at `~/.blocklife-keys/.env`, **outside the project
directory**. Claude Code auto-indexes the working directory on
startup; keeping keys external means there's nothing sensitive to
discover.

```bash
mkdir -p ~/.blocklife-keys
cp env.template ~/.blocklife-keys/.env
chmod 600 ~/.blocklife-keys/.env
# Edit ~/.blocklife-keys/.env: fill in MAIN_OPERATOR_KEY, MAIN_OWNER_KEY
# Add more accounts as needed: FARM1_OPERATOR_KEY=, FARM1_OWNER_KEY=
```

### 5. Configure the public roster (in the repo)

```bash
cp accounts/roster.yaml.template accounts/roster.yaml
# Edit accounts/roster.yaml: fill in the matching public addresses
# for each label (must match the LABEL prefixes in .env).
```

The MCP server cross-checks `~/.blocklife-keys/.env` against
`accounts/roster.yaml` on startup and warns on mismatches.

### 6. Enable secret-file deny rules + hook

```bash
cp .claude/settings.json.template .claude/settings.json
```

This installs deny rules and a `PreToolUse` hook that block any tool
call attempting to read `.env`, `*.key`, `*.pem`, or paths under
`~/.blocklife-keys/`. The agent itself never needs those — only the
MCP server does, and it loads them outside Claude Code's tool surface.

### 7. Configure the MCP server in Claude Code

Add the kamigotchi executor to your Claude Code MCP config. Either at
the project level (`./.mcp.json` in this repo, committed) or
user-global. Project-level is recommended:

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

### 8. Smoke-test the harness

```bash
cd executor
python3 -m pytest tests/ -v
```

Expected: **3 passed** (catalog reads — `test_expected_objective.py`)
and **3 skipped** (chain-state snapshots — `test_quest_state.py`,
which skip cleanly when no live account is loaded). If you see import
errors, your Python environment isn't set up correctly; revisit step 3.

---

## Mode A: Hybrid — interactive Claude Code

You'll run Claude Code on your laptop, in this repo, and chat with it
to play the game.

### Start a session

```bash
cd kami-harness
claude
```

In your first session, bootstrap the account:

```
list_accounts()                       # see what's configured
register_kamibots(account="main")     # owner-signed, populates API key
store_operator_key(account="main")    # encrypted at rest on Kamibots
get_tier(account="main")              # confirms API access
get_account_kamis(account="main")     # discover your kamis
```

After bootstrap, give Claude high-level direction. Examples:

> "Level kami 45 to L20 with a guardian build."
>
> "Check Q15 status and complete it if possible."
>
> "Move all kamis on node 8 over to node 12; node 8 is overcrowded."

Claude will perceive state, plan, execute via MCP tools, and report
results. Read [`CLAUDE.md`](CLAUDE.md) for the agent's operational
guidance — what it reads, what it executes, and what guardrails exist.

### Persistence

Per-session state lives in `memory/` (gitignored by default — uncomment
the line in `.gitignore` to commit it if you want shared memory across
machines). For most hybrid users it's fine to leave gitignored.

---

## Mode B: Fully autonomous — VM with cron

You'll provision a small cloud VM, install Claude Code there, and use
cron to trigger sessions on a schedule. The agent writes its own
schedule (`memory/next-run-at`) and commits decisions back to git.

### Architecture

```
   cron (every 15 min)
        │
        ▼
   scripts/run-session.sh ──reads── memory/next-run-at  (skip if not yet time)
        │
        ▼
   claude -p "$(cat session-prompt.md)" --dangerously-skip-permissions
        │  ├── reads CLAUDE.md, memory/plan.md, systems/, catalogs/
        │  ├── calls MCP tools (executor/server.py)
        │  ├── writes memory/decisions.md, memory/next-run-at
        │  └── git add memory/ && git commit && git push
        │
        ▼
   sleep until next cron firing
```

### Setup

1. **Provision a small VM**. e2-small on GCP (~$13/mo) or equivalent
   on any cloud is enough. Linux (Debian/Ubuntu) recommended. ~2 GB
   RAM.

2. **Install dependencies on the VM**:
   - Python 3.11+
   - Node.js (for the Claude Code CLI)
   - Claude Code CLI ([installation](https://docs.claude.com/en/docs/claude-code/quickstart))
   - Authenticate Claude Code via SSH port-forward OAuth flow (the docs explain headless auth)

3. **Set up a deploy key** on the VM with **write** access to your
   private fork of this repo. The agent will commit + push session
   logs to that fork.

4. **Clone your fork on the VM**:
   ```bash
   ssh you@your-vm
   git clone git@github.com:<you>/kami-harness.git
   cd kami-harness
   ```

5. **Run common setup steps 3–8 above** on the VM (Python deps, keys
   at `~/.blocklife-keys/.env`, roster, settings.json, MCP server,
   smoke test).

6. **Create your session prompt**:
   ```bash
   cp session-prompt.md.example session-prompt.md
   # Edit session-prompt.md to add any standing directives for the
   # agent — e.g., which account label to play, current strategic focus.
   ```

7. **Configure the cron runner**:
   ```bash
   cp scripts/run-session.sh.example scripts/run-session.sh
   # Edit scripts/run-session.sh — set REPO_DIR, LOG_FILE paths.
   chmod +x scripts/run-session.sh
   ```

8. **Add the cron entry**:
   ```bash
   crontab -e
   ```
   Add (every 15 minutes — the script self-skips if not yet time per
   `memory/next-run-at`):
   ```
   */15 * * * * /home/you/kami-harness/scripts/run-session.sh
   ```

9. **Trigger the first run manually** to bootstrap state:
   ```bash
   echo 0 > memory/next-run-at   # force immediate run on next cron
   # …or run the script directly to see live output:
   ./scripts/run-session.sh
   tail -f ~/kamigotchi-session.log
   ```

   In the first session the agent will call `register_kamibots`,
   `store_operator_key`, perceive state, and write its first
   `memory/plan.md`.

### Operating

- **Watch the log**: `tail -f ~/kamigotchi-session.log` shows live
  session output.
- **Review decisions**: `memory/decisions.md` is the agent's append-only
  decision log — committed every session. Review periodically.
- **Inject directives**: prepend a `Priority 0:` block at the top of
  `memory/plan.md`, commit + push from your laptop, then run
  `echo 0 > memory/next-run-at` on the VM (or wait for the next cron
  firing). The agent reads `plan.md` first thing every session.
- **Stop the agent**: comment out the cron line, or set
  `memory/next-run-at` to a far-future timestamp.

### Cost notes

- VM: ~$13/mo for e2-small.
- Claude Code: a Max subscription absorbs autonomous-mode session
  cost. API-billed runs work too but cost grows with session length /
  context.
- Yominet gas is flat 0.0025 gwei — gameplay txs are essentially
  free. Owner wallet just needs a small ETH balance to cover thousands
  of operator-signed txs.

---

## Troubleshooting

### `Account 'main' not found. Available: ...`
The MCP server scanned `~/.blocklife-keys/.env` for `*_OPERATOR_KEY` /
`*_OWNER_KEY` pairs. The label you passed (e.g. `main`) didn't match.
Check that `MAIN_OPERATOR_KEY=…` (uppercased) is set in
`~/.blocklife-keys/.env`.

### Tests fail with `no row in catalogs/quests/quests.csv`
The quest catalogs are committed in `catalogs/quests/`. If they're
missing, you have an incomplete clone — `git pull` to refresh.

### `register_kamibots` fails with a signature error
The owner key in `.env` doesn't match the owner address in
`roster.yaml`, or the owner address isn't actually the on-chain owner
of the operator. Recheck both.

### Agent runs out of gas on a large harvest_start batch
Default gas limits assume a 20-kami batch fits in Yominet's lane gas
limit. For >20 kamis split into smaller batches at the call site.
`harvest_start`'s gas was bumped from 1.5M → 3M after observed OOG
on node-change waves.

### Session times out at 30 minutes (autonomous mode)
That's the safety cap in `run-session.sh`. If you genuinely need
longer sessions, raise `SESSION_TIMEOUT` — but a 30-min run that
hasn't completed is usually a sign the agent is stuck. Check the log.

---

## Next steps

- Read [`README.md`](README.md) — the agent's view of game mechanics
  and decision priorities.
- Read [`CLAUDE.md`](CLAUDE.md) — operational instructions for the
  playing agent.
- Read [`executor/README.md`](executor/README.md) — the full MCP tool
  reference (64 tools across reads, on-chain actions, batch wrappers,
  trading, quests, scavenge).
- Review [`integration/system-ids.md`](integration/system-ids.md) and
  [`integration/entity-ids.md`](integration/entity-ids.md) if you want
  to extend the harness with custom tools.
