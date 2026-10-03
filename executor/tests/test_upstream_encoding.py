"""Every contract call this server encodes exists upstream — statically.

The defect this file exists for: pool_swap encoded
`executeTyped(uint32,uint32,uint256,uint256)` for system.pool, a function
the pool system does not have (its function is `swap`). Every hermetic
test passed, because the fake chain accepted whatever the harness
encoded; every live swap was refused by its own dry-run. Nothing in
3.7.0 tied an encoding to the game's real ABI.

Here, offline and without importing a chain: tests/tools/encoding_table.py
reads server.py's AST, finds every place an ABI constant meets a target
(system, component, World), and every (target, function, argument types,
return types) must exist in the vendored upstream ABI
(fixtures/upstream_abi/upstream_abi.json, generated from the game
repository at the pinned commit by tests/tools/vendor_upstream_abi.py).
The selector table committed beside it is what the code derives, so the
table handed to the chain audit cannot drift from the code.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "tools"))
import encoding_table as et  # noqa: E402

PINNED_UPSTREAM = "ffda396330af1bc33238b6c37188772152b45439"


@pytest.fixture(scope="module")
def model():
    return et.build_model()


@pytest.fixture(scope="module")
def doc():
    return et.upstream()


def test_the_vendored_abi_names_its_source(doc):
    p = doc["provenance"]
    assert p["commit"] == PINNED_UPSTREAM
    assert p["repository"].endswith("/kamigotchi")
    assert p["generator"] == "executor/tests/tools/vendor_upstream_abi.py"
    pool = doc["abis"][doc["systems"]["system.pool"]["abi"]]
    assert pool["swap(uint32,uint32,uint256,uint256)"][0] == "0x4a4f0718"
    assert "executeTyped(uint32,uint32,uint256,uint256)" not in pool


def test_every_encoded_call_exists_upstream(model, doc):
    """THE test. A wrong function name, argument type or return type on
    any system, component or World call fails here, offline."""
    problems = et.check(model, doc)
    assert problems == [], "\n".join(problems)


def test_the_check_bites_on_the_3_7_0_pool_encoding(model, doc):
    old = [{"type": "function", "name": "executeTyped",
            "inputs": [{"type": "uint32"}, {"type": "uint32"},
                       {"type": "uint256"}, {"type": "uint256"}],
            "outputs": [{"type": "bytes"}], "stateMutability": "nonpayable"}]
    mutated = et.Model(abis={**model.abis, "_ABI_POOL_SWAP": old},
                       consts=model.consts, bindings=[
                           (et.Binding(b.target, b.abi, b.func, b.line,
                                       {"executeTyped"}, b.signer, b.via)
                            if b.abi == "_ABI_POOL_SWAP" else b)
                           for b in model.bindings])
    problems = et.check(mutated, doc)
    assert any("executeTyped(uint32,uint32,uint256,uint256)" in p
               and "system.pool" in p for p in problems)


def test_every_abi_constant_is_bound_to_a_target_or_standard(model):
    bound = {b.abi for b in model.bindings}
    loose = set(model.abis) - bound - set(et.STANDARD_ABIS)
    assert loose == set(), (
        f"ABI constants with no upstream target found: {sorted(loose)} — "
        f"bind them where a tool uses them, or delete them")


def test_every_send_site_is_resolved(model):
    assert model.unresolved == []


# Resolution sites whose id is not a literal at the call: each must be a
# described send helper, a parametric helper (bound at its callers), or
# one of these, named with where its targets are checked.
NON_LITERAL_SITES = {
    ("_seq_prefetch_reads", "subjects[key][0]"): "EXTRA_READS (raw safeGet)",
    ("act_sequence", "system_id"): "the _seq_plan step tuples",
}


def test_every_non_literal_resolution_is_accounted_for(model):
    tree = ast.parse(et.SERVER.read_text())
    unknown = []
    for f in tree.body:
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(f):
            if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in inner.args.args}
            for n in ast.walk(inner):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                        and n.func.id in ("_resolve_system", "_resolve_component")
                        and n.args):
                    continue
                a = n.args[0]
                text = ast.unparse(a)
                if isinstance(a, ast.Constant) or text in model.consts:
                    continue
                if isinstance(a, ast.Name) and a.id in params and (
                        inner.name in et.SEND_HELPERS
                        or inner.name in model.parametric):
                    continue
                if (f.name, text) in NON_LITERAL_SITES:
                    continue
                if any(b.func == f.name and b.via == "eth.contract"
                       for b in model.bindings) and isinstance(a, ast.Name):
                    continue        # a local loop over literal ids, bound
                unknown.append(f"{f.name}:{n.lineno} {text}")
    assert unknown == []


def test_every_system_and_component_id_named_in_server_exists_upstream(doc):
    known = set(doc["systems"]) | set(doc["components"])
    pat = re.compile(r"^(system|component)\.[A-Za-z0-9._]+$")
    bad = sorted({n.value for n in ast.walk(ast.parse(et.SERVER.read_text()))
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and pat.match(n.value) and n.value not in known})
    assert bad == []


def test_the_committed_selector_table_is_what_the_code_encodes(model, doc):
    """Regenerate with: python3 tests/tools/encoding_table.py --write"""
    assert et.build_table(model, doc) == json.loads(et.TABLE.read_text())


def test_table_selectors_are_their_signatures(doc):
    table = json.loads(et.TABLE.read_text())
    for r in table["writes"] + table["reads"]:
        if r["selector"] is not None:
            assert r["selector"] == et.sel(r["signature"]), r
        up = et.upstream_fns(doc, r["target"])
        if up is not None:
            assert r["signature"] in up, r


def test_every_act_tool_and_every_sending_meta_tool_has_a_write_row():
    import server
    table = json.loads(et.TABLE.read_text())
    tools = {r["tool"] for r in table["writes"]}
    act = {t for t, c in server.TOOL_CLASSES.items() if c == "ACT"}
    assert act - tools == set()
    sending_meta = {"fund_operator", "withdraw_operator", "bridge_eth_from_mainnet"}
    assert sending_meta <= tools
    assert {r["tool"] for r in table["writes"]} - set(server.TOOL_CLASSES) == {
        "(any sending tool)"}


def test_pool_swap_is_tabled_as_upstream_swap():
    table = json.loads(et.TABLE.read_text())
    rows = [r for r in table["writes"] if r["tool"] == "pool_swap"]
    assert rows == [{"tool": "pool_swap", "target": "system.pool",
                     "signature": "swap(uint32,uint32,uint256,uint256)",
                     "selector": "0x4a4f0718", "signer": "operator"}]
