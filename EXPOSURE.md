# EXPOSURE — READ-tool registry

One row per READ tool on the MCP surface (a READ tool signs no
transaction and changes no remote state). Columns: the tool's surface
class, what the answer exposes, the named community/web-client
precedent for that exposure, the serving path, and the date the tool
was admitted to the surface. Deferred rows record reads that are
deliberately NOT served at this version — a visible entry, never a
silent absence.

The CI test `test_tool_surface.py::test_exposure_rows` fails when a
READ tool on the live registry has no row here, and when the deferred
rows below go missing.

## Served

| Tool | Class | Exposure | Precedent | Serving path | Admitted |
|---|---|---|---|---|---|
| `lens_kami` | PERCEIVE | one kami's live vitals + leveling; opt-in stat block + affinities | official web client kami panel | kami-lens daemon socket | 2026-07-23 |
| `lens_account` | PERCEIVE | account identity, room, stamina, roster; opt-in identity-only form (no roster) | official web client account panel | kami-lens daemon socket | 2026-07-23 |
| `lens_party` | PERCEIVE | one account's kamis with vitals (first 50; opt-in full list, opt-in stat block) | official web client party view | kami-lens daemon socket | 2026-07-23 |
| `lens_roster` | PERCEIVE | one line per kami (index, state, HP) + the account's room; opt-in stat block, which caps the list | official web client party sidebar | kami-lens daemon socket | 2026-08-25 |
| `lens_skills` | PERCEIVE | skill registry; one kami's unspent points + invested skills | official web client skill tree | kami-lens daemon socket | 2026-08-28 |
| `lens_node` | PERCEIVE | node occupancy (first 50); opt-in occupant vitals + liquidation preview, opt-in full row list, opt-in stat block, opt-in eligible-only filter | official web client node/liquidation view | kami-lens daemon socket | 2026-07-23 |
| `lens_room` | PERCEIVE | room occupancy (first 50 accounts + kami counts; the kamis themselves on the full form) | official web client room view | kami-lens daemon socket | 2026-07-23 |
| `lens_inventory` | PERCEIVE | any account's item balances | official web client inventory panel | kami-lens daemon socket | 2026-07-23 |
| `lens_item` | PERCEIVE | one item registry row | official web client item tooltip | kami-lens daemon socket | 2026-07-23 |
| `lens_items` | PERCEIVE | full item registry; opt-in ids + description prose | official web client item registry | kami-lens daemon socket | 2026-07-23 |
| `lens_config` | PERCEIVE | one on-chain config field | on-chain public config entities | kami-lens daemon socket | 2026-07-23 |
| `lens_merchant` | PERCEIVE | NPC listings + prices (gating as text); opt-in whole listing rows | official web client shop UI | kami-lens daemon socket | 2026-07-23 |
| `lens_phase` | PERCEIVE | world day/night phase + timer | official web client phase clock | kami-lens daemon socket | 2026-07-23 |
| `lens_leaderboard` | PERCEIVE | Score leaderboard rows, first 50 (mirror components); opt-in every row | official web client leaderboards | kami-lens daemon socket | 2026-07-23 |
| `lens_killers` | PERCEIVE | all-time kill ranking (service order) | official web client kill ranking (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_battles` | PERCEIVE | one kami's battle history | official web client battle log (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_trades` | PERCEIVE | open trades, first 50; per-account history; opt-in every trade + names | official web client trade UI (Kamiden) | kami-lens daemon socket (+ Kamiden history) | 2026-07-23 |
| `lens_auctions` | PERCEIVE | auctions + GDA price; buy history | official web client auction UI (Kamiden) | kami-lens daemon socket (+ Kamiden history) | 2026-07-23 |
| `lens_quests` | PERCEIVE | quest registry; per-account acceptance; opt-in uncompacted registry | official web client quest log | kami-lens daemon socket | 2026-07-23 |
| `lens_market` | PERCEIVE | KamiSwap listings/bids, first 50 of each; order history; opt-in every row + names | KamiSwap web UI (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_portal` | PERCEIVE | per-account portal history + withdrawals | official web client portal UI (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_transfers` | PERCEIVE | per-account item transfer history | official web client transfer log (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_feed` | PERCEIVE | buffered world feed events | official web client feed ticker (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_chat` | PERCEIVE | room chat page (flag-gated, default off) | official web client chat (Kamiden) | kami-lens daemon socket → Kamiden | 2026-07-23 |
| `lens_status` | PERCEIVE | lens daemon health/config incl. blocks behind chain head and per-feed degradation (no world state) | daemon self-report | kami-lens daemon socket | 2026-07-23 |
| `get_expected_objective` | PERCEIVE | quest catalog expectations (documentation, not chain truth) | community quest catalog export | local catalogs/ CSVs | ≤ v1.5.1 (2026-07-19); lens migration n/a (local catalog) |
| `check_quest_completable` | PERCEIVE | act-guard: would quest-complete revert now | official web client complete button state | chain staticCall | ≤ v1.5.1 (2026-07-19); kept native as an ACT pre-check |
| `quest_state` | PERCEIVE | one quest's on-chain state discriminated | official web client quest log | chain component reads | ≤ v1.5.1 (2026-07-19); kept native as an ACT pre-check |
| `get_scavenge_points` | PERCEIVE | per-account scavenge points + claimable tiers | official web client scavenge panel | chain component reads | ≤ v1.5.1 (2026-07-19); lens migration deferred visibly (no lens scavenge query at pin 8b74007) |
| `get_scavenge_droptable` | PERCEIVE | node droptable weights/probabilities | official web client scavenge panel | Kamibots nodes endpoint (node metadata) + chain component reads (weights) | ≤ v1.5.1 (2026-07-19); lens migration deferred visibly (no lens scavenge query at pin 8b74007) |
| `get_item_orderbook` | PERCEIVE | one item's complete order book | in-game World Order Book (kwob) | chain event-scan + component reads | ≤ v1.5.1 (2026-07-19); lens migration deferred visibly (per-item book exceeds lens_trades at this pin) |
| `pool_swap_quote` | PERCEIVE | priced quote for one pool swap: amount out, min received, price impact | in-game swap panel quote | chain component reads (live reserves + fee) | 2.1.0 (2026-08-07); kept native as an ACT pre-check — the perception layer carries pool reserves, the per-trade quote is the act's own |
| `get_tier` | OUTSOURCE | account tier/tax/slots at the strategy service | Kamibots dashboard | Kamibots API | ≤ v1.5.1 (2026-07-19) |
| `get_all_strategies` | OUTSOURCE | account's strategy list | Kamibots dashboard | Kamibots API | ≤ v1.5.1 (2026-07-19) |
| `get_all_strategy_statuses` | OUTSOURCE | live strategy container statuses | Kamibots dashboard | Kamibots API | ≤ v1.5.1 (2026-07-19) |
| `get_strategy_status` | OUTSOURCE | one kami's strategy status | Kamibots dashboard | Kamibots API | ≤ v1.5.1 (2026-07-19) |
| `get_strategy_logs` | OUTSOURCE | one strategy container's log tail | Kamibots dashboard | Kamibots API | ≤ v1.5.1 (2026-07-19) |
| `list_accounts` | META | local roster labels + public addresses | standard multi-wallet tooling | local roster/env | ≤ v1.5.1 (2026-07-19) |
| `get_gas_balance` | META | wallet gas balances | standard EVM wallet balance view | Yominet RPC | ≤ v1.5.1 (2026-07-19); wallet infra, not world state |
| `bridge_status` | META | one bridge transfer's state | Initia bridge widget/tracker | Initia router API + RPC | ≤ v1.5.1 (2026-07-19) |

## Deferred — visible, not served at this version

| Read | Status | Reason |
|---|---|---|
| guild-members | deferred | the Kamibots guild-members read left the surface with the world-state read removal (2026-07-23); no lens guild query exists at pin `8b74007` |
| general-leaderboards | deferred | the Kamibots `/api/leaderboards/{harvest,kill}` read left the surface (2026-07-23; upstream answered 500s in 2026-07); `lens_leaderboard` serves mirror Score components only |
| quest-status-natives | superseded | get_active_quests and get_quest_status left the surface in the 2.0.0 budget trim (2026-07-23, pre-approved): lens_quests and quest_state serve the same reads |
| windowed-killers | deferred | `lens_killers` is the all-time ranking; the time-windowed variant is upstream ApiKey-gated at lens pin `8b74007` and is not served |
| room-exit gates | served, not as a tool | room-exit access conditions reach the surface only as `travel_to_room`'s planning and refusals (`catalogs/room-gates.csv`, extracted from the lens `room` query during the 3.4.0 build, at the then-current pin `f07b578`; the gate data is chain state and unchanged at `8b74007`). No tool answers "what gates room N" on its own; `lens_room` serves the daemon's `exits[].gates` verbatim for a caller that wants the live form |

## Error classes a READ can raise

A caller must be able to tell "the world says no" from "the daemon
cannot answer yet". Both are named classes; neither is a generic
failure, and neither reads as an empty result.

| Class | Raised when | Why it is not the other one |
|---|---|---|
| `LensQueryError` | the daemon answered an error envelope (`BAD_ARGS`, `NOT_FOUND`, `KAMIDEN_UNAVAILABLE`, `CHAT_DISABLED`, ...); code and message pass through verbatim (SPEC P5) | the daemon is serving and this is its answer |
| `LensUnavailableError` | the socket is unreachable, unresponsive, or the mirror is uninitialised | no answer exists; retrying later is the remedy |
| `LensNotReadyError` (subclass of the above, code `NOT_READY`, served from lens 0.5.2) | a world read arrives while daemon `state != LIVE` | before 0.5.2 this was served as `NOT_FOUND: node 9 not in mirror`, which reads as "that node does not exist" and sends a caller hunting a missing entity instead of waiting for a sync |

## ACT coverage — game actions not served at this version

Sweep of every player-facing system at upstream pin `ef898fc`
(2026-07-23) against the ACT surface. Actions listed here are
deliberately visible gaps, never silent ones. Quest-completion
sufficiency does NOT depend on any row below: no quest objective or
requirement references them.

The three documented-mechanic gaps found by the sweep (skill-respec,
cast-item, newbie-vendor-buy) were resolved post-sweep (2026-07-23):
all three are now served by the `skill_respec`, `cast_item`, and
`newbie_vendor_buy` tools.

Documented in the game-mechanics docs (systems/*.md):

| Action | System | Status | Note |
|---|---|---|---|
| set-operator | `system.account.set.operator` | deferred | operator rebind; the operator lifecycle is otherwise served by create_operator_wallet + register_account |

Not documented in the game-mechanics docs:

| Action | System | Status | Note |
|---|---|---|---|
| account-bio / account-pfp / account-rename | `system.account.set.bio` / `.set.pfp` / `.set.name` | deferred | profile management |
| friends | `system.friend.request/accept/cancel/block` | deferred | social graph |
| goals | `system.goal.contribute` / `system.goal.claim` | deferred | community goals |
| gacha-ticket-eth-mint | `system.buy.gacha.ticket` | deferred | ETH purchase path; tickets are served via auction_buy / listing_buy / trading |
| npc-sell | `system.listing.sell` | deferred | selling items to NPC merchants |
| onyx-rename / onyx-respec | `system.kami.onyx.rename` / `system.kami.onyx.respec` | deferred | onyx-paid alternatives to name_kami / skill-respec |
| kami-721-bridge | `system.kami721.stake` / `.unstake` + 721 transfer | deferred | moving kamis across the world/ERC-721 boundary |
| token-portal | `system.erc20.portal` | deferred | token deposits/withdrawals (history readable via lens_portal) |
| npc-relationships | `system.relationship.advance` | deferred | NPC dialogue advancement |
