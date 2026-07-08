# Trading

P2P item trading and the Kami marketplace.

## P2P Item Trading

Orderbook model with a 3-step flow: **Create → Execute → Complete**.

### Structure Constraints

- Exactly **one item** on buy side, exactly **one item** on sell side
- **One side must be Musu** (item 1) — no pure barter
- Both sides cannot be Musu
- Items must not be flagged `NOT_TRADABLE`

### Trade Lifecycle

**Step 1: Create** (Maker posts offer)
- Define what you want to buy and what you're selling
- Sell-side items go into **escrow** (removed from inventory)
- Optionally target a specific taker account
- Fees: creation fee + delivery fee (waived in room 66)

**Step 2: Execute** (Taker fulfills)
- Taker sends buy-side items to escrow
- Taker receives sell-side items from escrow (after tax)
- Delivery fee charged (waived in room 66)

**Step 3: Complete** (Maker confirms)
- Maker receives buy-side items from escrow (after tax)
- Trade entity cleaned up
- Delivery fee charged (waived in room 66)

**Cancel** (Maker only, while PENDING)
- Sell-side items returned from escrow
- Delivery fee charged

### Fees & Tax Config (Read On-Chain)

These config keys control all trade costs. Read at startup via
`component.value` using `keccak256("is.config", configName)`:

| Config Key | Indices Used | Controls |
|---|---|---|
| `TRADE_TAX_RATE` | `[0]` = precision exp, `[1]` = numerator | Tax on Musu leaving escrow |
| `TRADE_CREATION_FEE` | `[0]` = amount (Musu) | Flat cost to create a trade |
| `TRADE_DELIVERY_FEE` | `[0]` = amount (Musu) | Flat cost per trade step (waived in room 66) |
| `KAMI_MARKET_FEE_RATE` | `[0]` = precision exp, `[1]` = numerator | Kami marketplace sale fee |

Config reading pattern:
```javascript
const configId = BigInt(ethers.keccak256(
  ethers.solidityPacked(["string", "string"], ["is.config", "TRADE_TAX_RATE"])
));
const raw = await valueComp.getValue(configId);
// Decode packed int32 array from raw uint256
```

### Fee Schedule

| Fee | Charged to | When | Formula |
|---|---|---|---|
| Creation fee | Maker | On create | `TRADE_CREATION_FEE[0]` Musu |
| Delivery fee | Whoever calls | On create, execute, complete, cancel | `TRADE_DELIVERY_FEE[0]` Musu |

Both fees paid in Musu. **Delivery fee is waived in room 66** (Marketplace).

### Trade Tax

Applied to **Musu** when it leaves escrow:

```
tax = amount * TRADE_TAX_RATE[1] / 10^TRADE_TAX_RATE[0]
```

Non-Musu items are not taxed. Tax is burned (not redistributed).

## Kami Marketplace

On-chain orderbook for trading Kami NFTs. Three order types.

### Listings (Sell Kami for ETH)

Owner wallet lists a Kami at a fixed ETH price.

1. Kami must be `RESTING` and not soulbound
2. Kami enters `LISTED` state (can't harvest, equip, etc.)
3. Kami stays in seller's wallet (no escrow)
4. Buyer pays ETH, receives Kami

Fee: `price * KAMI_MARKET_FEE_RATE[1] / 10^KAMI_MARKET_FEE_RATE[0]` (read from config, see above).

**Purchase cooldown**: 1 hour after buying — Kami can't act immediately.

### Specific Offers (Buy a Kami for WETH)

Buyer offers WETH for a specific Kami by index.

- Requires pre-approval of `KamiMarketVault` to spend WETH
- No transfer until seller accepts
- Seller receives WETH minus fee

### Collection Offers (Buy Any Kami for WETH)

Buyer offers WETH per Kami, quantity N.

- Any Kami owner can accept (selling into the offer)
- Balance decrements per fill
- Auto-completes when balance reaches 0

Newly purchased Kamis have a 1-hour cooldown before they can act. Newbie
vendor purchases are soulbound for 3 days.

## How to Execute

### P2P Trades

All use **Owner** wallet.

**Create** — `system.trade.create`
```
executeTyped(uint32[] buyIndices, uint256[] buyAmts, uint32[] sellIndices, uint256[] sellAmts, uint256 targetID)
```
Pass `targetID = 0` for open trade.

**Execute** — `system.trade.execute`
```
executeTyped(uint256 tradeID)
```

**Complete** — `system.trade.complete`
```
executeTyped(uint256 tradeID)
```

**Cancel** — `system.trade.cancel`
```
executeTyped(uint256 tradeID)
```

### Kami Marketplace

**List** — `system.kami.market.list` (Owner)
```
executeTyped(uint32 kamiIndex, uint256 price, uint256 expiry)
```

**Buy listing** — `system.kami.market.buy` (Owner)
```
executeTyped(uint256[] listingIDs)   // send ETH as msg.value
```

**Make offer** — `system.kami.market.offer` (Owner)
```
executeTyped(bool isCollection, uint32 kamiIndex, uint256 price, uint256 quantity, uint256 expiry)
```

**Accept offer** — `system.kami.market.accept.offer` (Owner)
```
executeTyped(bool isBatch, uint256 offerID, uint32 kamiIndex, uint32[] kamiIndices)
```

**Cancel order** — `system.kami.market.cancel` (Owner)

## Cross-References

- Room 66 location: [rooms.md](rooms.md)
- NPC shop prices (alternative to trading): [npc-shops.md](npc-shops.md)
- Item catalog (tradability): [catalogs/items.csv](../catalogs/items.csv)
- Marketplace state via indexer: [state-reading.md](state-reading.md)
