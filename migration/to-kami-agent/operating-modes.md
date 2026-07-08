# Operating modes (cut verbatim from `SETUP.md`)

These sections were removed from the `kami-harness` `SETUP.md` during the
environment-interface refactor. They describe how an *agent* is run
against the harness (interactive vs headless/cron), which is agent
runtime policy, not environment setup. Preserved verbatim for migration
into `kami-agent`.

The parts of the old `SETUP.md` that configure the **environment**
itself (Python deps, wallet keys, roster, MCP server config, smoke test)
stayed in `kami-harness` `SETUP.md`.

---

## Two operating modes (SETUP intro)

| Mode | Best for | Loop |
|---|---|---|
| **A. Hybrid** | Testing, iteration, supervised play, learning the harness | Interactive Claude Code session on your laptop. You give direction, the agent executes via MCP tools, you review. |
| **B. Fully autonomous** | 24/7 quest grinds, long unattended runs | Claude Code runs headless on a small VM, triggered by cron. Agent reads its own plan, perceives, acts, commits + pushes. No human in the loop during the session. |

Both modes share the same harness — only the runtime wrapper differs.

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

## Autonomous-mode troubleshooting (SETUP)

### Session times out at 30 minutes (autonomous mode)
That's the safety cap in `run-session.sh`. If you genuinely need
longer sessions, raise `SESSION_TIMEOUT` — but a 30-min run that
hasn't completed is usually a sign the agent is stuck. Check the log.
