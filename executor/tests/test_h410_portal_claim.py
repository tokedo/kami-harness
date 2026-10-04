"""4.1.0 — `portal_claim` reports the payout, never a gas leg.

On Yominet gas is paid in the same ERC-20 the portal pays out (Ether
Shard 103's token). Every transaction's receipt therefore carries two
Transfer logs of that token besides the game's own: the gas PREPAYMENT
(the sender to a fee collector, first) and the unused-gas REFUND (the fee
collector back to the sender, last). A live claim on 2026-10-04 carried
three Transfers of the token at log indices 0, 9 and 15:

    0   sender -> fee collector         4,562,760,000,001   gas prepayment
    9   token holder -> payee          90,000,000,000,000   the payout
    15  fee collector -> sender         2,176,567,500,000   gas refund

and 4.0.0 reported the LAST one (the refund) as `amount_wei`, and the
refund's recipient (the signer) as `payee`.

The game's own record of a claim, the `PORTAL_TOKEN_CLAIM` world event,
carries (timestamp, account id, receipt id) only — no payee, no amount
(upstream LibTokenPortal.emitClaim at the pin). The payout is therefore
the Transfer of the token FROM the portal's token holder
(`component.token.holder`, the only payer in upstream's claim) TO the
payee computed before signing, and its value must equal the receipt's
token amount read before signing. The claimed token is pinned: a
Transfer on any other contract is never the payout. Anything else is a
`decode_error`, never a silently wrong amount.

Synthetic addresses throughout; the values and the log order are the
live claim's.
"""

from __future__ import annotations

import eth_abi
import pytest
from eth_utils import keccak

import server
from conftest import KEY_A
from fakenode import addr_for
from test_400_surface import ETH_TOKEN, ROTATED, TRANSFER, WORLD_EVENT
from test_400_surface import portal_env  # noqa: F401  (fixture)
from test_h400_send_path import chain_env  # noqa: F401  (fixture)

FEE_COLLECTOR = "0x" + "fc" * 20          # synthetic
ELSEWHERE = "0x" + "e1" * 20              # synthetic
OTHER_TOKEN = "0x" + "de" * 20            # synthetic: not the claimed token

PREPAY_WEI = 4_562_760_000_001
PAYOUT_WEI = 90_000_000_000_000
REFUND_WEI = 2_176_567_500_000

# 10 Ether Shards withdrawn, export tax 1 item (flat 1 + 50 bps of 10),
# 9 net at scale 5: 9 x 10^13 wei — the live claim's payout.
ITEMS = 10
COMPONENT_WRITE = "0x" + keccak(
    b"ComponentValueSet(uint256,address,uint256,bytes)").hex()
CLAIM_EVENT = "0x" + keccak(b"PORTAL_TOKEN_CLAIM").hex()


def _word(addr: str) -> str:
    return "0x" + "00" * 12 + addr.lower().removeprefix("0x")


def _transfer(src: str, dst: str, value: int, token: str = ETH_TOKEN):
    return (token.lower(), [TRANSFER, _word(src), _word(dst)],
            eth_abi.encode(["uint256"], [value]))


def _component_writes(n: int, start: int):
    """Game logs that are not Transfers (the receipt's component writes)."""
    return [(addr_for("component.value"),
             [COMPONENT_WRITE, "0x" + (start + i).to_bytes(32, "big").hex(),
              _word(addr_for("component.value")), "0x" + "00" * 32], b"")
            for i in range(n)]


def _claim_event(portal, rid: int):
    value = eth_abi.encode(["uint256", "uint256", "uint256"],
                           [int(portal.clock.now), portal.aid, rid])
    return (addr_for("emitter"), [WORLD_EVENT, CLAIM_EVENT],
            eth_abi.encode(["uint8[]", "bytes"], [[13, 13, 13], value]))


def _gas_legged_claim(portal_env, order="chain", payout=None):
    """Re-install the fake portal's claim so its receipt carries the gas
    legs around the game's logs, as the chain's does.

    order="chain": prepayment, 8 component writes, the payout, 4 writes
    and the claim event, refund — the payout at log index 9, the gas
    legs at 0 and 15, as on the live claim. order="reversed": the same
    logs back to front (no rule may depend on log order).
    payout(logs, sender) -> logs rewrites the game's payout Transfer.
    """
    node, game, clock, portal, split = portal_env
    plain = portal._claim

    def claim(n, caller, args, commit):
        (rid,) = eth_abi.decode(["uint256"], args)
        res = plain(n, caller, args, commit)
        if not commit or res.status != 1:
            return res
        paid = res.logs if payout is None else payout(res.logs, caller.sender)
        logs = ([_transfer(caller.sender, FEE_COLLECTOR, PREPAY_WEI)]
                + _component_writes(8, 0) + list(paid)
                + _component_writes(4, 8) + [_claim_event(portal, rid)]
                + [_transfer(FEE_COLLECTOR, caller.sender, REFUND_WEI)])
        res.logs = logs if order == "chain" else logs[::-1]
        return res

    node.handle(addr_for("system.erc20.portal"), "claim(uint256)", claim)


def _receipt(portal_env, to: str):
    node, game, clock, portal, split = portal_env
    rid = server.portal_withdraw(103, ITEMS, to=to, account="split")["receipt_id"]
    assert portal.receipts[int(rid, 16)]["wei"] == PAYOUT_WEI
    clock.sleep(43_201)
    return rid


def _mined_receipt(node, tx_hash):
    return node.receipts[tx_hash.lower()]


def _assert_tx_fields(node, out):
    """The transaction's own fields come from its receipt, whatever the
    decode found."""
    r = _mined_receipt(node, out["tx_hash"])
    assert out["status"] == "success"
    assert out["block"] == int(r["blockNumber"], 16)
    assert out["gas_used"] == int(r["gasUsed"], 16)


def test_the_live_claim_layout_puts_the_payout_between_the_gas_legs(
    portal_env,
):
    """The fixture is the live claim: three Transfers of the token at
    log indices 0, 9, 15, in that order, with the live values."""
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")
    _gas_legged_claim(portal_env)
    out = server.portal_claim(rid, account="split")
    logs = _mined_receipt(node, out["tx_hash"])["logs"]
    transfers = [(int(lg["logIndex"], 16), int(lg["data"], 16))
                 for lg in logs if lg["topics"][0] == TRANSFER]
    assert transfers == [(0, PREPAY_WEI), (9, PAYOUT_WEI), (15, REFUND_WEI)]


# ---------------------------------------------------------------------------
# 1 — signer = payee
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("order", ["chain", "reversed"])
@pytest.mark.parametrize("lane", ["operator", "owner"])
def test_a_claim_signed_by_its_payee_reports_the_payout_not_the_refund(
    portal_env, lane, order,
):
    """Operator-lane receipt signed by the operator, or owner receipt
    signed by the owner: the signer IS the payee, so the gas refund is a
    Transfer to the payee too — it is not the payout."""
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, lane)
    _gas_legged_claim(portal_env, order)
    out = server.portal_claim(rid, account="split")
    signer = split.operator_addr if lane == "operator" else split.owner_addr
    assert portal.claim_sender == signer.lower()
    assert out["payee"] == signer
    assert out["amount_wei"] == "90000000000000"
    assert out["amount"] == "0.00009"
    assert "decode_error" not in out
    assert out["route"] == lane
    _assert_tx_fields(node, out)


# ---------------------------------------------------------------------------
# 2 — signer != payee
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("order", ["chain", "reversed"])
@pytest.mark.parametrize("case", ["no operator key here", "operator rotated"])
def test_an_owner_signed_operator_lane_claim_reports_the_operator_payout(
    portal_env, monkeypatch, case, order,
):
    """The owner signs an operator-lane receipt; the payout goes to the
    operator and the gas refund to the owner. The refund is the only
    Transfer to the signer — it is neither the payee nor the amount."""
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")
    if case == "no operator key here":
        account = "owner-only"
        monkeypatch.setitem(server._accounts, account,
                            server._Account(account, None, KEY_A))
        payee = split.operator_addr
    else:
        account = "split"
        portal.operator = ROTATED.lower()
        payee = ROTATED
    _gas_legged_claim(portal_env, order)
    out = server.portal_claim(rid, account=account)
    assert portal.claim_sender == split.owner_addr.lower()
    assert out["payee"].lower() == payee.lower()
    assert out["payee"].lower() != split.owner_addr.lower()
    assert out["amount_wei"] == "90000000000000"
    assert out["amount"] == "0.00009"
    assert "decode_error" not in out
    _assert_tx_fields(node, out)


# ---------------------------------------------------------------------------
# 3 — no payout identifiable
# ---------------------------------------------------------------------------

def _no_payout(logs, sender):
    return []


def _payout_elsewhere(logs, sender):
    """The token holder paid someone who is not the payee computed
    before signing."""
    return [_transfer(addr_for("component.token.holder"), ELSEWHERE,
                      PAYOUT_WEI)]


def _payout_from_elsewhere(logs, sender):
    """A Transfer of the right value to the payee, not from the token
    holder (the portal pays only out of its holder)."""
    return [_transfer(ELSEWHERE, sender, PAYOUT_WEI)]


def _two_payouts(logs, sender):
    return list(logs) + list(logs)


@pytest.mark.parametrize("payout, needle", [
    (_no_payout, "no payout"),
    (_payout_elsewhere, "no payout"),
    (_payout_from_elsewhere, "no payout"),
    (_two_payouts, "2 Transfers"),
])
def test_a_claim_whose_payout_cannot_be_identified_says_so(
    portal_env, payout, needle,
):
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")
    _gas_legged_claim(portal_env, payout=payout)
    out = server.portal_claim(rid, account="split")
    assert out["amount_wei"] is None
    assert "amount" not in out
    assert needle in out["decode_error"]
    assert out["payee"] is None
    _assert_tx_fields(node, out)


# ---------------------------------------------------------------------------
# 4 — payout value != the receipt's token amount read before sending
# ---------------------------------------------------------------------------

def test_a_payout_that_disagrees_with_the_receipt_amount_names_both(
    portal_env,
):
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")
    short = PAYOUT_WEI - 10 ** 13

    def underpaid(logs, sender):
        return [_transfer(addr_for("component.token.holder"), sender, short)]

    _gas_legged_claim(portal_env, payout=underpaid)
    out = server.portal_claim(rid, account="split")
    assert out["payee"] == split.operator_addr     # the payout was found
    assert out["amount_wei"] is None               # its value is not trusted
    assert "amount" not in out
    err = out["decode_error"]
    assert str(short) in err and str(PAYOUT_WEI) in err
    _assert_tx_fields(node, out)


# ---------------------------------------------------------------------------
# 5 — the claimed token is pinned: a Transfer on another contract is never
#     the payout, whoever sent it and whatever its value
# ---------------------------------------------------------------------------

def _decoy(sender, value=PAYOUT_WEI):
    """The holder paying the payee, with the receipt's exact value, on a
    contract that is not the claimed token."""
    return _transfer(addr_for("component.token.holder"), sender, value,
                     token=OTHER_TOKEN)


def test_a_transfer_on_another_token_is_not_the_payout(portal_env):
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")
    _gas_legged_claim(portal_env,
                      payout=lambda logs, sender: [_decoy(sender)])
    out = server.portal_claim(rid, account="split")
    assert out["payee"] is None
    assert out["amount_wei"] is None
    assert "amount" not in out
    assert "no payout" in out["decode_error"]
    _assert_tx_fields(node, out)


@pytest.mark.parametrize("decoy_value", [PAYOUT_WEI, PAYOUT_WEI + 1])
@pytest.mark.parametrize("where", ["before", "after"])
def test_with_a_decoy_on_another_token_the_claimed_tokens_transfer_is_the_payout(
    portal_env, where, decoy_value,
):
    node, game, clock, portal, split = portal_env
    rid = _receipt(portal_env, "operator")

    def with_decoy(logs, sender):
        decoy = [_decoy(sender, decoy_value)]
        return decoy + list(logs) if where == "before" else list(logs) + decoy

    _gas_legged_claim(portal_env, payout=with_decoy)
    out = server.portal_claim(rid, account="split")
    assert out["payee"] == split.operator_addr
    assert out["amount_wei"] == "90000000000000"
    assert out["amount"] == "0.00009"
    assert "decode_error" not in out
    _assert_tx_fields(node, out)
