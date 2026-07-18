"""Offline tests for the v1.5.0 droptable/sacrifice reveal fix.

Covers string/hex commit-ID parsing (including exact round-trips above
IEEE-754 float precision), the estimate-gas preflight (raises the
validation marker, sends nothing), the scavenge_claim_and_reveal
retry/expiry paths, and regression coverage that the touched tools
still fail their v1.4.0 validation cases identically. No network,
keys, or chain access.
"""

from types import SimpleNamespace

import pytest

from conftest import FAKE_ACCOUNT_ID

import server

# A real-scale uint256 commit entity ID — far above 2^53, where IEEE-754
# doubles lose integer precision.
BIG_ID = int.from_bytes(bytes(range(224, 256)), "big")


# ---------------------------------------------------------------------------
# _parse_commit_id
# ---------------------------------------------------------------------------


class TestParseCommitId:
    def test_int_passthrough(self):
        assert server._parse_commit_id(BIG_ID) == BIG_ID

    def test_decimal_string(self):
        assert server._parse_commit_id(str(BIG_ID)) == BIG_ID

    def test_hex_string_either_prefix_case(self):
        assert server._parse_commit_id(hex(BIG_ID)) == BIG_ID
        assert server._parse_commit_id("0X" + format(BIG_ID, "X")) == BIG_ID

    def test_surrounding_whitespace(self):
        assert server._parse_commit_id(f"  {BIG_ID} ") == BIG_ID

    def test_above_float_precision_round_trips_exactly(self):
        v = 2**53 + 1  # smallest integer a double cannot represent
        assert float(v) == v - 1  # the mangling the string form avoids
        parsed = server._parse_commit_id(str(v))
        assert parsed == v
        assert str(parsed) == str(v)

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            server._parse_commit_id("not-a-number")


# ---------------------------------------------------------------------------
# Reveal-path fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reveal_chain(monkeypatch):
    """Fake droptable-reveal system contract with a settable
    estimate_gas handler; identity system resolution; block 1000."""
    state = {"estimate": lambda ids: 100_000, "estimate_calls": []}

    class _Fns:
        def executeTyped(self, ids):
            def estimate(params):
                state["estimate_calls"].append(ids)
                return state["estimate"](ids)

            return SimpleNamespace(estimate_gas=estimate)

    contract = SimpleNamespace(functions=_Fns())
    eth = SimpleNamespace(
        contract=lambda address=None, abi=None: contract,
        block_number=1_000,
    )
    monkeypatch.setattr(server, "w3", SimpleNamespace(eth=eth))
    monkeypatch.setattr(server, "_resolve_system", lambda sid: sid)
    monkeypatch.setattr(
        server, "_require_registered_operator", lambda a: FAKE_ACCOUNT_ID
    )
    return state


# ---------------------------------------------------------------------------
# droptable_reveal: estimated gas + preflight
# ---------------------------------------------------------------------------


class TestDroptableRevealGas:
    def test_parses_strings_and_sends_estimate_x1_5(
        self, accounts, reveal_chain, sent
    ):
        reveal_chain["estimate"] = lambda ids: 8_000_000  # large claim
        r = server.droptable_reveal([str(BIG_ID), "0x10"], account="testa")
        assert r["status"] == "success"
        assert reveal_chain["estimate_calls"] == [[BIG_ID, 16]]
        assert sent[0]["system"] == "system.droptable.item.reveal"
        assert sent[0]["args"] == [[BIG_ID, 16]]
        assert sent[0]["gas_limit"] == 12_000_000  # estimate x 1.5

    def test_preflight_revert_raises_marker_sends_nothing(
        self, accounts, reveal_chain, sent
    ):
        def boom(ids):
            raise ValueError(
                {"code": -32000, "message": "execution reverted: no seed"}
            )

        reveal_chain["estimate"] = boom
        with pytest.raises(server.PreTxValidationError) as ei:
            server.droptable_reveal([str(BIG_ID)], account="testa")
        msg = str(ei.value)
        assert msg.startswith("validation failed; no transaction sent: ")
        assert "reveal gas estimation reverted" in msg
        assert "execution reverted: no seed" in msg
        assert "256 blocks" in msg
        assert sent == []


# ---------------------------------------------------------------------------
# scavenge_claim: commit IDs returned as decimal strings
# ---------------------------------------------------------------------------


class TestScavengeClaimStringIds:
    def test_commit_ids_are_decimal_strings(
        self, accounts, validation_ok, monkeypatch
    ):
        monkeypatch.setattr(
            server, "get_scavenge_points",
            lambda node, account: {
                "points": 200, "tier_cost": 100, "claimable_tiers": 2,
            },
        )
        monkeypatch.setattr(
            server, "_extract_commit_ids", lambda receipt: [BIG_ID]
        )

        def fake_send(account, system_id, abi, args, gas_limit=None,
                      return_receipt=False):
            res = {
                "tx_hash": "0xabc", "status": "success", "block": 5,
                "gas_used": 1, "account": account,
            }
            if return_receipt:
                res["_receipt"] = SimpleNamespace(logs=[])
            return res

        monkeypatch.setattr(server, "_send_tx", fake_send)
        r = server.scavenge_claim(16, account="testa")
        assert r["commit_ids"] == [str(BIG_ID)]
        assert all(isinstance(c, str) for c in r["commit_ids"])
        assert int(r["commit_ids"][0]) == BIG_ID  # exact, no float transit


# ---------------------------------------------------------------------------
# scavenge_claim_and_reveal: retry + honest expiry reporting
# ---------------------------------------------------------------------------


class TestClaimAndRevealRetry:
    @pytest.fixture(autouse=True)
    def _claim(self, monkeypatch):
        monkeypatch.setattr(
            server, "scavenge_claim",
            lambda node, account: {
                "status": "success", "block": 10,
                "commit_ids": [str(BIG_ID)],
            },
        )
        monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def test_retry_succeeds_on_second_attempt(
        self, accounts, reveal_chain, sent
    ):
        attempts = {"n": 0}

        def flaky(ids):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ValueError("execution reverted: same block")
            return 500_000

        reveal_chain["estimate"] = flaky
        r = server.scavenge_claim_and_reveal(16, account="testa")
        assert "error" not in r and "reveal_skipped" not in r
        assert r["reveal"]["status"] == "success"
        assert r["commit_ids"] == [str(BIG_ID)]
        assert attempts["n"] == 2
        assert len(sent) == 1

    def test_exhausted_retries_report_factually(
        self, accounts, reveal_chain, sent
    ):
        attempts = {"n": 0}

        def always(ids):
            attempts["n"] += 1
            raise ValueError("execution reverted: blockhash unavailable")

        reveal_chain["estimate"] = always
        r = server.scavenge_claim_and_reveal(16, account="testa")
        assert attempts["n"] == 3
        assert sent == []  # every attempt died in preflight
        assert r["reveal"] is None
        assert r["claim"]["status"] == "success"
        assert r["commit_ids"] == [str(BIG_ID)]
        assert "reveal failed after 3 attempts" in r["error"]
        assert "blockhash unavailable" in r["last_failure"]
        assert r["last_failure"].startswith(
            "validation failed; no transaction sent: "
        )
        assert "256 blocks" in r["error"]
        assert "claim block 10" in r["error"]
        # v1.4.0 mislabel removed; no operational advice in the text.
        assert "reveal_skipped" not in r
        assert "granted directly by claim" not in str(r)
        assert "escalate" not in str(r).lower()
        assert "incident" not in str(r).lower()

    def test_onchain_revert_reported_as_itself(
        self, accounts, reveal_chain, monkeypatch
    ):
        reveal_chain["estimate"] = lambda ids: 100_000

        def reverted(account, system_id, abi, args, **kw):
            return {
                "tx_hash": "0xdead", "status": "reverted", "block": 11,
                "gas_used": 100_000, "account": account,
            }

        monkeypatch.setattr(server, "_send_tx", reverted)
        r = server.scavenge_claim_and_reveal(16, account="testa")
        assert r["reveal"]["status"] == "reverted"
        assert "reveal failed after 3 attempts" in r["error"]
        assert "reverted on-chain" in r["last_failure"]
        assert "0xdead" in r["last_failure"]
        assert "reveal_skipped" not in r


# ---------------------------------------------------------------------------
# Regression: v1.4.0 validation cases fail identically
# ---------------------------------------------------------------------------


class TestV140ValidationUnchanged:
    def test_droptable_reveal_empty_guard(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError,
            match="commit_ids is empty; droptable_reveal requires at least",
        ):
            server.droptable_reveal([], account="testa")
        assert sent == []

    def test_scavenge_claim_tier_gate(
        self, accounts, validation_ok, sent, monkeypatch
    ):
        monkeypatch.setattr(
            server, "get_scavenge_points",
            lambda node, account: {
                "points": 5, "tier_cost": 100, "claimable_tiers": 0,
            },
        )
        with pytest.raises(server.PreTxValidationError) as ei:
            server.scavenge_claim(16, account="testa")
        msg = str(ei.value)
        assert "has 5 scavenge points at node 16" in msg
        assert "claiming a tier requires 100" in msg
        assert sent == []

    def test_sacrifice_reveal_empty_guard(self, accounts, sent):
        with pytest.raises(
            server.PreTxValidationError,
            match="commit_ids is empty; pass the ids returned by",
        ):
            server.sacrifice_reveal([], account="testa")
        assert sent == []

    def test_droptable_reveal_requires_registered_operator(
        self, accounts, reveal_chain, sent, monkeypatch
    ):
        def unregistered(account):
            raise server.PreTxValidationError(
                f"no account is registered for operator 0x0 "
                f"(account '{account}')"
            )

        monkeypatch.setattr(
            server, "_require_registered_operator", unregistered
        )
        with pytest.raises(
            server.PreTxValidationError, match="no account is registered"
        ):
            server.droptable_reveal([str(BIG_ID)], account="testa")
        assert reveal_chain["estimate_calls"] == []  # gate precedes preflight
        assert sent == []
