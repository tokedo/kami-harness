"""Offline tests for the kami-lens PERCEIVE wrappers (2.0.0-dev, H2).

A real unix-domain-socket JSON-lines server stands in for the daemon:
argument mapping is asserted against the captured request, envelopes
pass through untouched (stale flags included), daemon-down and
query-level errors surface as their distinct classes, and the
presentation/chat knobs behave. No network, keys, or chain access.
"""

import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest

import server


@pytest.fixture()
def short_dir():
    """AF_UNIX socket paths are capped (~104 bytes on macOS); pytest's
    tmp_path is too deep, so sockets live in a short mkdtemp dir."""
    d = Path(tempfile.mkdtemp(prefix="kl-"))
    yield d
    shutil.rmtree(d, ignore_errors=True)

ENVELOPE = {
    "data": {"index": 45, "name": "Momo"},
    "untrusted": ["name"],
    "meta": {
        "servedAt": "2026-07-23T00:00:00Z",
        "blockNumber": 123456,
        "stale": False,
        "mode": "daemon",
    },
}


@pytest.fixture()
def lens(short_dir, monkeypatch):
    """JSON-lines unix-socket stub; returns a namespace with captured
    requests and a settable responder."""
    sock_path = short_dir / "kami-lens.sock"
    state = {
        "requests": [],
        # responder(req) -> dict merged over {id, ok}
        "responder": lambda req: {"ok": True, **ENVELOPE},
    }

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(4)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                buf = b""
                while b"\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                if not buf.strip():
                    continue
                req = json.loads(buf.split(b"\n", 1)[0])
                state["requests"].append(req)
                resp = {"id": req.get("id"), **state["responder"](req)}
                conn.sendall((json.dumps(resp) + "\n").encode())

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    monkeypatch.setattr(server, "KAMI_LENS_SOCKET", str(sock_path))
    yield state
    srv.close()


class TestArgumentMapping:
    CASES = [
        (lambda: server.lens_kami(45), "kami", ["45"]),
        (lambda: server.lens_account("tokedo"), "account", ["tokedo"]),
        (lambda: server.lens_account(""), "account", None),
        (lambda: server.lens_party(7), "party", ["7"]),
        (lambda: server.lens_party(), "party", None),
        (lambda: server.lens_node(86), "node", ["86"]),
        (
            lambda: server.lens_node(86, with_vitals=True),
            "node", ["86", "--with-vitals"],
        ),
        (
            lambda: server.lens_node(86, with_vitals=True, attacker_kami_index=45),
            "node", ["86", "45", "--with-vitals"],
        ),
        (lambda: server.lens_room(19), "room", ["19"]),
        (lambda: server.lens_inventory("7"), "inventory", ["7"]),
        (lambda: server.lens_item(11302), "item", ["11302"]),
        (lambda: server.lens_items(), "items", None),
        (lambda: server.lens_config("KAMI_LVL_REQ"), "config", ["KAMI_LVL_REQ"]),
        (
            lambda: server.lens_config("KAMI_LVL_REQ", array=True),
            "config", ["KAMI_LVL_REQ", "--array"],
        ),
        (lambda: server.lens_merchant(), "merchant", None),
        (lambda: server.lens_merchant(1), "merchant", ["1"]),
        (lambda: server.lens_phase(), "phase", None),
        (
            lambda: server.lens_leaderboard(),
            "leaderboard", ["COLLECT", "1", "1"],
        ),
        (
            lambda: server.lens_leaderboard("FEED", 2, 11302),
            "leaderboard", ["FEED", "2", "11302"],
        ),
        (lambda: server.lens_killers(), "killers", ["50"]),
        (lambda: server.lens_killers(10), "killers", ["10"]),
        (lambda: server.lens_battles(45), "battles", ["45"]),
        (
            lambda: server.lens_battles(45, before_ms=1700000000000),
            "battles", ["45", "1700000000000"],
        ),
        (lambda: server.lens_trades(), "trades", None),
        (lambda: server.lens_trades(7), "trades", ["7"]),
        (lambda: server.lens_auctions(), "auctions", None),
        (lambda: server.lens_auctions(10), "auctions", ["10"]),
        (lambda: server.lens_quests(), "quests", None),
        (lambda: server.lens_quests(7), "quests", ["7"]),
        (lambda: server.lens_market(), "market", None),
        (lambda: server.lens_portal(7), "portal", ["7"]),
        (lambda: server.lens_transfers(7), "transfers", ["7"]),
        (lambda: server.lens_feed(), "feed", None),
        (lambda: server.lens_feed(100, "KILL"), "feed", ["100", "KILL"]),
        (lambda: server.lens_status(), "status", None),
    ]

    def test_every_wrapper_maps_args(self, lens):
        for call, query, args in self.CASES:
            lens["requests"].clear()
            call()
            req = lens["requests"][-1]
            assert req["query"] == query, query
            assert req.get("args") == args, (query, req.get("args"))

    def test_prose_flag_passes_through(self, lens):
        server.lens_account("tokedo", prose=True)
        assert lens["requests"][-1].get("prose") is True
        server.lens_account("tokedo")
        assert "prose" not in lens["requests"][-1]


class TestEnvelopePassThrough:
    def test_envelope_verbatim(self, lens):
        r = server.lens_kami(45)
        assert r == ENVELOPE  # data, untrusted, meta — nothing reshaped

    def test_stale_and_suppressed_pass_through(self, lens):
        stale = {
            "data": {"x": 1},
            "untrusted": [],
            "meta": {"servedAt": "t", "blockNumber": 5, "stale": True,
                     "mode": "daemon", "suppressed": ["name"]},
        }
        lens["responder"] = lambda req: {"ok": True, **stale}
        r = server.lens_items()
        assert r["meta"]["stale"] is True
        assert r["meta"]["suppressed"] == ["name"]

    def test_status_degraded_passes_through(self, lens):
        status = {
            "data": {"state": "LIVE", "degraded": ["STREAM_SILENT"]},
            "untrusted": [],
            "meta": {"servedAt": "t", "blockNumber": 9, "stale": True,
                     "mode": "daemon"},
        }
        lens["responder"] = lambda req: {"ok": True, **status}
        r = server.lens_status()
        assert r["data"]["degraded"] == ["STREAM_SILENT"]


class TestLensUnavailable:
    def test_no_socket_file(self, short_dir, monkeypatch):
        monkeypatch.setattr(
            server, "KAMI_LENS_SOCKET", str(short_dir / "absent.sock")
        )
        with pytest.raises(server.LensUnavailableError) as ei:
            server.lens_kami(45)
        msg = str(ei.value)
        assert "LENS_UNAVAILABLE" in msg
        assert "daemon state: unreachable" in msg
        assert "absent.sock" in msg

    def test_mirror_not_initialized_is_unavailable(self, lens):
        lens["responder"] = lambda req: {
            "ok": False,
            "error": {"code": "NOT_FOUND",
                      "message": "mirror not initialized yet"},
        }
        with pytest.raises(server.LensUnavailableError) as ei:
            server.lens_kami(45)
        assert "daemon state: starting" in str(ei.value)

    def test_connection_closed_before_answer(self, short_dir, monkeypatch):
        sock_path = short_dir / "dead.sock"
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)

        def slam():
            conn, _ = srv.accept()
            conn.close()

        threading.Thread(target=slam, daemon=True).start()
        monkeypatch.setattr(server, "KAMI_LENS_SOCKET", str(sock_path))
        with pytest.raises(server.LensUnavailableError, match="closed the"):
            server.lens_kami(45)
        srv.close()


class TestQueryErrors:
    def test_not_found_passes_through(self, lens):
        lens["responder"] = lambda req: {
            "ok": False,
            "error": {"code": "NOT_FOUND", "message": "kami 999999 not in mirror"},
        }
        with pytest.raises(server.LensQueryError) as ei:
            server.lens_kami(999999)
        assert ei.value.code == "NOT_FOUND"
        assert "kami 999999 not in mirror" in str(ei.value)

    def test_kamiden_unavailable_passes_through(self, lens):
        lens["responder"] = lambda req: {
            "ok": False,
            "error": {"code": "KAMIDEN_UNAVAILABLE", "message": "feed down"},
        }
        with pytest.raises(server.LensQueryError, match="KAMIDEN_UNAVAILABLE"):
            server.lens_killers()


class TestPresentationMode:
    def test_name_free_requests_no_authored(self, lens, monkeypatch):
        monkeypatch.setattr(server, "PRESENTATION_MODE", "name-free")
        server.lens_kami(45)
        assert lens["requests"][-1].get("noAuthored") is True

    def test_envelope_mode_sends_no_flag(self, lens):
        server.lens_kami(45)
        assert "noAuthored" not in lens["requests"][-1]

    def test_mode_validation(self):
        assert server._validate_presentation_mode("envelope") == "envelope"
        assert server._validate_presentation_mode("name-free") == "name-free"
        with pytest.raises(RuntimeError, match="not implemented"):
            server._validate_presentation_mode("inline-tags")
        with pytest.raises(RuntimeError, match="not one of"):
            server._validate_presentation_mode("bogus")


class TestChatFlag:
    def test_disabled_by_default_no_socket_contact(self, lens, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", False)
        with pytest.raises(server.LensQueryError, match="CHAT_DISABLED"):
            server.lens_chat(19)
        assert lens["requests"] == []

    def test_enabled_passes_through(self, lens, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        server.lens_chat(19)
        req = lens["requests"][-1]
        assert req["query"] == "chat" and req["args"] == ["19"]

    def test_oversize_flag(self, lens, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        server.lens_chat(19, oversize=True)
        assert lens["requests"][-1].get("oversize") is True

    def test_size_requires_before(self, lens, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        with pytest.raises(ValueError, match="size requires before_ms"):
            server.lens_chat(19, size=5)
        assert lens["requests"] == []

    def test_paging_args(self, lens, monkeypatch):
        monkeypatch.setattr(server, "CHAT_ENABLED", True)
        server.lens_chat(19, before_ms=1700000000000, size=5)
        assert lens["requests"][-1]["args"] == ["19", "1700000000000", "5"]
