"""4.3.0 — the last release before the freeze (part 1).

J1  `dry_run` on portal_deposit, portal_claim and portal_cancel
J2  a fee total wherever a result sums gas; gas fields on gap-fill rows
J3  the two lane texts 4.2.0 left behind; fund_operator states the
    prepayment

All hermetic: the fake portal and fake node of the 4.0.0 / 4.2.0 tests.
"""

from __future__ import annotations

import pytest

import server
from test_400_surface import ETH_TOKEN, ONYX_TOKEN, portal_env  # noqa: F401
from test_h400_send_path import chain_env  # noqa: F401  (fixture)

PRICE = 2_500_000                     # the flat price, wei per gas
# The fake portal's estimates x 1.5 (the limits the portal sends with),
# and the prepayment bound _gas_fee_bound states for each (+ 1 wei).
DEPOSIT_BOUND = 750_000 * PRICE + 1   # deposit: 500,000 -> 750,000
APPROVE_BOUND = 90_000 * PRICE + 1    # approve:  60,000 ->  90,000
SETTLE_BOUND = 450_000 * PRICE + 1    # claim / cancel: 300,000 -> 450,000
ITEMS = 5                             # Ether Shard 103, scale 5
WEI = ITEMS * 10 ** 13


def _fund(portal, split, held, allowance, token=ETH_TOKEN):
    owner, t = split.owner_addr.lower(), token.lower()
    portal.token_bal[(t, owner)] = held
    portal.allowance[(t, owner)] = allowance


def _no_terminal_state(out):
    """A dry run has no terminal state (SPEC P4): no status, no hash."""
    assert out["dry_run"] is True
    for k in ("status", "tx_hash", "block", "gas_used", "fee_wei", "txs"):
        assert k not in out, (k, out)


# ---------------------------------------------------------------------------
# J1 — dry_run on the three portal tools that lacked it
# ---------------------------------------------------------------------------

def test_a_deposit_dry_run_quotes_and_signs_nothing(portal_env):  # noqa: F811
    """Allowance covering: the token amount, no approve, the deposit's fee
    bound, the gas-token rule's verdict — and not one transaction."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND, allowance=WEI)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends
    assert out["token"]["amount_wei"] == str(WEI)
    assert out["credited"] == ITEMS - 1                  # tax 1
    assert out["approve_needed"] is False
    assert out["approve_fee_bound_wei"] is None
    assert out["deposit_fee_bound_wei"] == str(DEPOSIT_BOUND)
    assert out["gas_token"] is True and out["gas_token_rule"] == "passes"
    assert game.inv[103] == 200_000                      # nothing deposited


def test_a_deposit_dry_run_refuses_as_the_real_call_does(portal_env):  # noqa: F811
    """The gas-token rule's refusal, with zero transactions: the same
    PreTxValidationError a real call raises."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + DEPOSIT_BOUND - 1, allowance=WEI)
    with pytest.raises(server.PreTxValidationError) as dry:
        server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        server.portal_deposit(103, ITEMS, account="split")
    assert str(dry.value) == str(real.value)
    assert "1 wei short" in str(dry.value)
    assert not node.sends


def test_a_deposit_dry_run_with_a_short_allowance_signs_no_approve(
    portal_env,  # noqa: F811
):
    """The approve would be needed: the dry run says so, states its bound,
    and signs nothing — not even the approve. The deposit cannot be
    estimated before its allowance exists, so its bound is null and the
    verdict says what was checked."""
    node, game, clock, portal, split = portal_env
    _fund(portal, split, WEI + APPROVE_BOUND, allowance=0)
    out = server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends and not portal.approvals
    assert out["approve_needed"] is True
    assert out["approve_fee_bound_wei"] == str(APPROVE_BOUND)
    assert out["deposit_fee_bound_wei"] is None
    assert out["gas_token_rule"].startswith("approve stage passes")

    _fund(portal, split, WEI + APPROVE_BOUND - 1, allowance=0)
    with pytest.raises(server.PreTxValidationError, match="1 wei short"):
        server.portal_deposit(103, ITEMS, account="split", dry_run=True)
    assert not node.sends and not portal.approvals


def test_a_deposit_dry_run_of_a_token_that_is_not_the_gas_token(portal_env):  # noqa: F811
    node, game, clock, portal, split = portal_env
    wei = 1_000 * 10 ** 16
    _fund(portal, split, wei, allowance=wei, token=ONYX_TOKEN)
    out = server.portal_deposit(100, 1_000, account="split", dry_run=True)
    _no_terminal_state(out)
    assert not node.sends
    assert out["gas_token"] is False
    assert out["gas_token_rule"] == "not the gas token"
    assert out["deposit_fee_bound_wei"] == str(DEPOSIT_BOUND)


def _receipt_at(portal_env, to="operator", wait=True):  # noqa: F811
    node, game, clock, portal, split = portal_env
    rid = server.portal_withdraw(103, 100_000, to=to,
                                 account="split")["receipt_id"]
    if wait:
        clock.sleep(43_201)
    return rid


def test_a_claim_dry_run_states_payee_route_amount_and_signs_nothing(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env)
    sent = len(node.sends)
    out = server.portal_claim(rid, account="split", dry_run=True)
    _no_terminal_state(out)
    assert len(node.sends) == sent
    assert int(rid, 16) in portal.receipts               # still pending
    assert out["receipt_id"] == rid and out["route"] == "operator"
    assert out["payee"].lower() == split.operator_addr.lower()
    assert out["amount_wei"] == str(99_499 * 10 ** 13)
    assert out["amount"] == "0.99499"
    assert out["claimable_now"] is True
    assert out["fee_bound_wei"] == str(SETTLE_BOUND)


def test_a_claim_dry_run_before_the_delay_refuses_as_the_real_call_does(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env, wait=False)
    sent = len(node.sends)
    with pytest.raises(server.PreTxValidationError) as dry:
        server.portal_claim(rid, account="split", dry_run=True)
    with pytest.raises(server.PreTxValidationError) as real:
        server.portal_claim(rid, account="split")
    assert str(dry.value) == str(real.value)
    assert "claimable at" in str(dry.value)
    assert len(node.sends) == sent


def test_a_claim_dry_run_names_a_payee_that_is_not_this_server(portal_env):  # noqa: F811
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env)
    portal.operator = ("0x" + "ab" * 20)
    out = server.portal_claim(rid, account="split", dry_run=True)
    assert next(iter(out)) == "notice" and "as of this claim" in out["notice"]
    assert out["payee"].lower() == "0x" + "ab" * 20


def test_a_cancel_dry_run_states_items_and_tax_and_signs_nothing(
    portal_env,  # noqa: F811
):
    node, game, clock, portal, split = portal_env
    rid = _receipt_at(portal_env, to="owner", wait=False)
    sent, inv = len(node.sends), game.inv[103]
    out = server.portal_cancel(rid, account="split", dry_run=True)
    _no_terminal_state(out)
    assert len(node.sends) == sent and game.inv[103] == inv
    assert int(rid, 16) in portal.receipts
    assert out["receipt_id"] == rid
    assert out["items_refunded"] == 99_499 and out["tax_not_refunded"] == 501
    assert out["fee_bound_wei"] == str(SETTLE_BOUND)


def test_the_three_portal_tools_take_an_optional_dry_run():
    tools = {t.name: t for t in server.mcp._tool_manager.list_tools()}
    for name in ("portal_deposit", "portal_claim", "portal_cancel"):
        props = tools[name].parameters["properties"]
        assert props.get("dry_run", {}).get("default") is False, name
        assert "dry_run" not in tools[name].parameters.get("required", [])
        assert "dry_run" in tools[name].description, name
