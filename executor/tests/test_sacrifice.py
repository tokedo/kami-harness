"""Offline tests for the sacrifice tools.

Covers sacrifice_kami, sacrifice_kami_batch, sacrifice_reveal, and the
commit-ID receipt extraction. No network, keys, or chain access.
"""

from types import SimpleNamespace

import pytest

from conftest import FakeContract

import server


def _receipt_with_commit(commit_id: int):
    match = SimpleNamespace(
        topics=[
            bytes.fromhex(server._STORE_SET_RECORD_EVENT),
            b"\x00" * 32,
            b"\x00" * 32,
            commit_id.to_bytes(32, "big"),
        ],
        data=b"\x00\x20" + server._SAC_COMMIT_MARKER,
    )
    other = SimpleNamespace(
        topics=[b"\xff" * 32, b"\x00" * 32], data=b"unrelated"
    )
    return SimpleNamespace(logs=[other, match, match])


class TestExtractCommitIds:
    def test_extracts_and_dedupes(self):
        ids = server._extract_sacrifice_commit_ids(_receipt_with_commit(1234))
        assert ids == [1234]

    def test_no_match(self):
        r = SimpleNamespace(
            logs=[SimpleNamespace(topics=[b"\xff" * 32], data=b"x")]
        )
        assert server._extract_sacrifice_commit_ids(r) == []


class TestSacrificeKami:
    def test_happy(self, accounts, chain, monkeypatch):
        chain["component.state"] = FakeContract({"safeGet": lambda eid: "RESTING"})
        chain["system.kami.sacrifice.commit"] = FakeContract(
            {"executeTyped": lambda ki: b""}
        )

        def fake_send(account, system_id, abi, args, gas_limit=None,
                      return_receipt=False):
            res = {
                "tx_hash": "0xabc",
                "status": "success",
                "block": 5,
                "gas_used": 1,
                "account": account,
            }
            if return_receipt:
                res["_receipt"] = _receipt_with_commit(1234)
            return res

        monkeypatch.setattr(server, "_send_tx", fake_send)
        r = server.sacrifice_kami(16403, account="testa")
        assert r["status"] == "success"
        assert r["commit_ids"] == [1234]
        assert r["kami_state"] == "RESTING"
        assert "_receipt" not in r

    def test_dry_run_revert_no_tx(self, accounts, chain, sent):
        chain["component.state"] = FakeContract({"safeGet": lambda eid: "HARVESTING"})

        def revert(ki):
            raise Exception("execution reverted: wrong room")

        chain["system.kami.sacrifice.commit"] = FakeContract(
            {"executeTyped": revert}
        )
        with pytest.raises(ValueError, match="room 19"):
            server.sacrifice_kami(16403, account="testa")
        assert sent == []


class TestSacrificeKamiBatch:
    def test_mixed_batch(self, accounts, chain, sent):
        def gate(ki):
            if ki == 2:
                raise Exception("execution reverted: not owner")
            return b""

        chain["system.kami.sacrifice.commit"] = FakeContract(
            {"executeTyped": gate}
        )
        r = server.sacrifice_kami_batch(
            [1, 2, 1], account="testa", delay_seconds=0
        )
        assert r["requested"] == 2  # duplicate de-duplicated
        assert r["submitted"] == 1 and r["skipped"] == 1
        statuses = {row["kami_id"]: row["status"] for row in r["results"]}
        assert statuses[1] == "success" and statuses[2] == "skipped"
        assert len(sent) == 1 and sent[0]["args"] == [1]

    def test_empty_raises(self, accounts, chain):
        with pytest.raises(ValueError, match="is empty"):
            server.sacrifice_kami_batch([], account="testa")


class TestSacrificeReveal:
    def test_happy_uses_batch_fn(self, accounts, sent):
        # v1.5.0: commit IDs cross the MCP boundary as strings (decimal
        # or 0x-hex in, decimal out); the on-chain call gets ints.
        r = server.sacrifice_reveal(["9", "0xa"], account="testa")
        assert r["status"] == "success"
        assert r["commit_ids"] == ["9", "10"]
        assert sent[0]["fn_name"] == "executeTypedBatch"
        assert sent[0]["args"] == [[9, 10]]

    def test_empty_raises(self, accounts, sent):
        with pytest.raises(ValueError, match="is empty"):
            server.sacrifice_reveal([], account="testa")
        assert sent == []
