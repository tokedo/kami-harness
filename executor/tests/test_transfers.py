"""Offline tests for transfer_kami and transfer_items.

All chain access (state/ownership pre-checks, dry-runs) and transaction
sending is faked; no network, keys, or chain access.
"""

import pytest

from conftest import FakeContract

import server


def _kami_chain(chain, state="RESTING", owner_eid=None, dry_run_error=None):
    chain["component.state"] = FakeContract({"safeGet": lambda eid: state})
    chain["component.id.kami.owns"] = FakeContract(
        {"safeGet": lambda eid: owner_eid}
    )

    def send(indices, addr):
        if dry_run_error:
            raise Exception(dry_run_error)
        return b""

    chain["system.kami.send"] = FakeContract({"executeTyped": send})


class TestTransferKami:
    def test_happy_roster_label(self, accounts, chain, sent):
        _kami_chain(
            chain, owner_eid=server._account_entity_id("testa")
        )
        r = server.transfer_kami([5], to_account="testb", account="testa")
        assert r["status"] == "success"
        assert r["destination"] == "testb"
        assert r["destination_operator"] == accounts["testb"].operator_addr
        assert r["per_kami"][0]["state"] == "RESTING"
        assert r["per_kami"][0]["owned_by_source"] is True
        assert sent[0]["gas_limit"] == 2_000_000
        assert sent[0]["args"][0] == [5]

    def test_happy_raw_address(self, accounts, chain, sent):
        _kami_chain(
            chain, owner_eid=server._account_entity_id("testa")
        )
        dest = accounts["testb"].operator_addr
        r = server.transfer_kami([5, 6], to_address=dest, account="testa")
        assert r["status"] == "success"
        assert r["destination"] == dest
        assert sent[0]["gas_limit"] == 3_000_000  # scales with batch size

    def test_dest_validation(self, accounts, chain, sent):
        with pytest.raises(ValueError, match="exactly one"):
            server.transfer_kami([5], account="testa")
        with pytest.raises(ValueError, match="exactly one"):
            server.transfer_kami(
                [5], to_account="testb", to_address="0x1", account="testa"
            )
        with pytest.raises(ValueError, match="not a valid address"):
            server.transfer_kami([5], to_address="0x123", account="testa")
        with pytest.raises(ValueError, match="not found"):
            server.transfer_kami([5], to_account="ghost", account="testa")
        with pytest.raises(ValueError, match="itself"):
            server.transfer_kami(
                [5],
                to_address=accounts["testa"].operator_addr,
                account="testa",
            )
        assert sent == []

    def test_batch_shape_validation(self, accounts, chain, sent):
        with pytest.raises(ValueError, match="is empty"):
            server.transfer_kami([], to_account="testb", account="testa")
        with pytest.raises(ValueError, match="duplicate"):
            server.transfer_kami([5, 5], to_account="testb", account="testa")
        with pytest.raises(ValueError, match="too many"):
            server.transfer_kami(
                list(range(10)), to_account="testb", account="testa"
            )
        assert sent == []

    def test_blocked_state_no_tx(self, accounts, chain, sent):
        _kami_chain(
            chain,
            state="HARVESTING",
            owner_eid=server._account_entity_id("testa"),
        )
        with pytest.raises(ValueError, match="RESTING or LISTED"):
            server.transfer_kami([5], to_account="testb", account="testa")
        assert sent == []

    def test_not_owned_no_tx(self, accounts, chain, sent):
        _kami_chain(chain, owner_eid=12345)  # someone else's kami
        with pytest.raises(ValueError, match="not owned by source"):
            server.transfer_kami([5], to_account="testb", account="testa")
        assert sent == []

    def test_dry_run_revert_no_tx(self, accounts, chain, sent):
        _kami_chain(
            chain,
            owner_eid=server._account_entity_id("testa"),
            dry_run_error="execution reverted: cooldown",
        )
        with pytest.raises(ValueError, match="dry-run reverted"):
            server.transfer_kami([5], to_account="testb", account="testa")
        assert sent == []


class TestTransferItems:
    def _xfer_chain(self, chain, dry_run_error=None):
        def xfer(indices, amts, target):
            if dry_run_error:
                raise Exception(dry_run_error)
            return b""

        chain["system.item.transfer"] = FakeContract({"executeTyped": xfer})

    def test_happy_roster_label(self, accounts, chain, sent):
        self._xfer_chain(chain)
        r = server.transfer_items(
            [30004, 30026], [1, 7], to_account="testb", account="testa"
        )
        assert r["status"] == "success"
        assert r["destination_owner"] == accounts["testb"].owner_addr
        assert r["fee_musu"] == 30
        assert sent[0]["args"] == [
            [30004, 30026],
            [1, 7],
            int(accounts["testb"].owner_addr, 16),
        ]

    def test_happy_raw_address(self, accounts, chain, sent):
        self._xfer_chain(chain)
        dest = accounts["testb"].owner_addr
        r = server.transfer_items([30004], [2], to_address=dest, account="testa")
        assert r["status"] == "success"
        assert r["destination"] == dest

    def test_requires_owner_key(self, accounts, chain, sent):
        with pytest.raises(ValueError, match="no owner key"):
            server.transfer_items(
                [30004], [1], to_account="testb", account="noown"
            )
        assert sent == []

    def test_shape_validation(self, accounts, chain, sent):
        with pytest.raises(ValueError, match="exactly one"):
            server.transfer_items([30004], [1], account="testa")
        with pytest.raises(ValueError, match="is empty"):
            server.transfer_items([], [], to_account="testb", account="testa")
        with pytest.raises(ValueError, match="same length"):
            server.transfer_items(
                [30004], [1, 2], to_account="testb", account="testa"
            )
        with pytest.raises(ValueError, match="duplicate"):
            server.transfer_items(
                [30004, 30004], [1, 1], to_account="testb", account="testa"
            )
        with pytest.raises(ValueError, match="> 0"):
            server.transfer_items(
                [30004], [0], to_account="testb", account="testa"
            )
        with pytest.raises(ValueError, match="too many"):
            server.transfer_items(
                list(range(101, 110)),
                [1] * 9,
                to_account="testb",
                account="testa",
            )
        assert sent == []

    def test_dry_run_revert_no_tx(self, accounts, chain, sent):
        self._xfer_chain(chain, dry_run_error="execution reverted")
        with pytest.raises(ValueError, match="MUSU/type fee"):
            server.transfer_items(
                [30004], [1], to_account="testb", account="testa"
            )
        assert sent == []
