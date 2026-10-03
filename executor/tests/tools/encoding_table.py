"""Every contract call server.py can encode, checked against upstream.

A static reading of server.py (no import, no chain): it finds each place
an ABI constant meets a target — a game system or component id, the
World, or an external token — and the function names called through it.
tests/test_upstream_encoding.py asserts that every such (target,
function, argument types, return types) exists in the vendored upstream
ABI (fixtures/upstream_abi/upstream_abi.json), and that the selector
table committed beside it (selector_table.json) is exactly what this
module derives, so the table cannot drift from the code.

    python3 tests/tools/encoding_table.py --write   # regenerate the table
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from eth_utils import keccak

EXECUTOR = Path(__file__).resolve().parents[2]
SERVER = EXECUTOR / "server.py"
FIXTURES = EXECUTOR / "tests" / "fixtures" / "upstream_abi"
UPSTREAM = FIXTURES / "upstream_abi.json"
TABLE = FIXTURES / "selector_table.json"

# Send helpers: where the system id, the ABI and the function name sit in
# the call, and which wallet signs. A call to a helper not listed here
# that pairs a system id with an ABI fails the coverage test, so a new
# send path has to be described before it can ship.
SEND_HELPERS = {
    # name: (system arg, abi arg, fn arg or None, default fn, signer)
    "_send_tx": (1, 2, None, "executeTyped", "operator"),
    "_send_tx_retry": (1, 2, None, "executeTyped", "operator"),
    "_send_tx_owner": (1, 2, None, "executeTyped", "owner"),
    "_send_batch_tx": (1, 2, 3, None, "operator"),     # use_owner=True -> owner
    "_validated_fn": (0, 1, 2, None, "dry-run"),
    "_diagnose_batch": (0, 1, None, "executeTyped", "dry-run"),
}

# Transactions server.py sends whose target is not a game system with an
# ABI constant in server.py. Each is stated by hand, with its reason.
EXTRA_WRITES = [
    {"tools": ["portal_withdraw"], "target": "system.erc20.portal",
     "signature": "withdraw(uint32,uint256)", "signer": "owner",
     "note": "to='owner'"},
    {"tools": ["portal_withdraw"], "target": "system.erc20.portal",
     "signature": "withdrawToOperator(uint32,uint256)", "signer": "operator",
     "note": "to='operator'"},
    {"tools": ["portal_claim"], "target": "system.erc20.portal",
     "signature": "claim(uint256)", "signer": "owner or current operator",
     "note": ""},
    {"tools": ["portal_cancel"], "target": "system.erc20.portal",
     "signature": "cancel(uint256)", "signer": "owner or current operator",
     "note": ""},
    {"tools": ["portal_deposit"], "target": "system.erc20.portal",
     "signature": "deposit(uint32,uint256)", "signer": "owner", "note": ""},
    {"tools": ["portal_deposit"], "target": "ERC-20 token (item's portal token)",
     "signature": "approve(address,uint256)", "signer": "owner",
     "note": "only when the allowance is short; spender = component.token.allowance"},
    {"tools": ["fund_operator"], "target": "the account's operator wallet",
     "signature": "(plain ETH transfer)", "signer": "owner",
     "note": "empty calldata"},
    {"tools": ["withdraw_operator"], "target": "the account's owner wallet",
     "signature": "(plain ETH transfer)", "signer": "operator",
     "note": "empty calldata"},
    {"tools": ["(any sending tool)"], "target": "own address",
     "signature": "(zero-value self-transfer)", "signer": "the lane's signer",
     "note": "nonce-gap fill"},
    {"tools": ["bridge_eth_from_mainnet"], "target": "Initia router (Ethereum mainnet)",
     "signature": "(calldata from router-api.initia.xyz)", "signer": "owner",
     "note": "UNVERIFIED here: the calldata is built by the router API, not by this module"},
]

# Raw eth_calls built by hand (no ABI constant): act_sequence's batched
# pre-send reads send safeGet(uint256) to these components.
EXTRA_READS = [
    {"tools": ["act_sequence"], "target": t, "signature": "safeGet(uint256)",
     "outputs": [o]}
    for t, o in (("component.id.kami.owns", "uint256"),
                 ("component.state", "string"),
                 ("component.value", "uint256"))
]

# ABI constants that are not bound to a game system or component.
STANDARD_ABIS = {
    "_ABI_ERC20": {
        "balanceOf(address)": ["uint256"],
        "allowance(address,address)": ["uint256"],
        "approve(address,uint256)": ["bool"],
    },
}


def _type(p: dict) -> str:
    t = p["type"]
    if t.startswith("tuple"):
        return f"({','.join(_type(c) for c in p.get('components', []))}){t[5:]}"
    return t


def _static(t: str) -> bool:
    return not (t.endswith("[]") or t in ("bytes", "string")
                or (t.startswith("(") and not all(
                    _static(x) for x in _split(t[1:-1]))))


def _split(inner: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += ch == "("
        depth -= ch == ")"
        cur += ch
    return out + ([cur] if cur else [])


def norm_outputs(outs: list[str]) -> list[str]:
    """A single static tuple return encodes exactly as its fields."""
    if len(outs) == 1 and outs[0].startswith("(") and outs[0].endswith(")") \
            and _static(outs[0]):
        return _split(outs[0][1:-1])
    return outs


def signature(fn: dict) -> str:
    return f"{fn['name']}({','.join(_type(i) for i in fn.get('inputs', []))})"


def sel(sig: str) -> str:
    return "0x" + keccak(text=sig)[:4].hex()


@dataclass
class Binding:
    target: str                 # system/component id, "world", "erc20", "registry"
    abi: str                    # ABI constant name
    func: str                   # enclosing function
    line: int
    fns: set | None = None      # function names called; None = every one
    signer: str = "read"
    via: str = ""
    value: bool = False          # the call sends ETH with it


@dataclass
class Model:
    abis: dict = field(default_factory=dict)        # name -> [fn dicts]
    consts: dict = field(default_factory=dict)      # name -> str
    bindings: list = field(default_factory=list)
    tools: dict = field(default_factory=dict)       # tool -> True
    parametric: dict = field(default_factory=dict)  # helper -> (arg, abi, fns)
    calls: dict = field(default_factory=dict)       # func -> set(called)
    unresolved: list = field(default_factory=list)  # (func, line, text)


def _json_value(node):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "loads" and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)):
        try:
            return json.loads(node.args[0].value)
        except ValueError:
            return None
    return None


def _target(node, consts) -> str | None:
    """A target id literal (or module constant holding one)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value
    elif isinstance(node, ast.Name) and node.id in consts:
        v = consts[node.id]
    else:
        return None
    if (v.startswith("system.") or v.startswith("component.")) and " " not in v:
        return v
    return None


def build_model() -> Model:
    tree = ast.parse(SERVER.read_text())
    m = Model()
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 \
                and isinstance(st.targets[0], ast.Name):
            name = st.targets[0].id
            val = _json_value(st.value)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                m.abis[name] = [e for e in val if e.get("type") == "function"]
            elif isinstance(st.value, ast.Name) and st.value.id in m.abis:
                m.abis[name] = m.abis[st.value.id]
            elif isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                m.consts[name] = st.value.value

    funcs = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    m.parametric = _parametric_helpers(funcs, m.abis)
    top = {f.name for f in tree.body
           if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for f in funcs:
        if any(ast.unparse(d) == "mcp.tool()" for d in f.decorator_list):
            m.tools[f.name] = True
        m.calls.setdefault(f.name, set()).update(
            n.func.id for n in ast.walk(f)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in top)
    # Bind within each TOP-LEVEL function: a nested helper's calls belong
    # to the function (and so the tools) that defines it.
    for f in tree.body:
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _bind_in(f, m)
    return m


def _fn_attrs(func, var: str) -> set:
    """Function names called as <var>.functions.<name> in func."""
    out = set()
    for n in ast.walk(func):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "functions"
                and isinstance(n.value.value, ast.Name) and n.value.value.id == var):
            out.add(n.attr)
    return out


def _bind_in(func, m: Model) -> None:
    abis, consts = m.abis, m.consts
    # local name -> literal targets it can hold (for-loop tuples, assigns)
    local_targets: dict[str, set] = {}
    for n in ast.walk(func):
        if isinstance(n, ast.For):
            names = [t.id for t in ast.walk(n.target) if isinstance(t, ast.Name)]
            lits = {t for t in (_target(c, consts) for c in ast.walk(n.iter)) if t}
            for nm in names:
                if lits:
                    local_targets.setdefault(nm, set()).update(lits)
    for n in ast.walk(func):
        # (0) a helper that resolves its own parameter: bind its literal
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id in m.parametric:
            idx, abi, fns = m.parametric[n.func.id]
            if len(n.args) > idx:
                tgt = _target(n.args[idx], consts)
                if tgt:
                    m.bindings.append(Binding(tgt, abi, func.name, n.lineno,
                                              fns or None, "read", n.func.id))
                else:
                    m.unresolved.append((func.name, n.lineno, ast.unparse(n)[:120]))
        # (1) send-helper calls and tuples pairing a target with an ABI
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id in SEND_HELPERS:
            si, ai, fi, default, signer = SEND_HELPERS[n.func.id]
            args = list(n.args)
            kw = {k.arg: k.value for k in n.keywords}
            if len(args) <= max(si, ai):
                continue
            tgt = _target(args[si], consts)
            abi = args[ai].id if isinstance(args[ai], ast.Name) else None
            if tgt is None or abi not in abis:
                if tgt is not None or abi in abis:
                    m.unresolved.append((func.name, n.lineno, ast.unparse(n)[:120]))
                continue
            fnode = kw.get("fn_name") if fi is None else (
                args[fi] if len(args) > fi else kw.get("fn_name"))
            fn = fnode.value if isinstance(fnode, ast.Constant) else default
            if n.func.id == "_send_batch_tx":
                uo = kw.get("use_owner")
                if isinstance(uo, ast.Constant) and uo.value is True:
                    signer = "owner"
            vnode = kw.get("value_wei") or (
                args[5] if n.func.id == "_send_tx_owner" and len(args) > 5 else None)
            sends_value = vnode is not None and not (
                isinstance(vnode, ast.Constant) and not vnode.value)
            m.bindings.append(Binding(tgt, abi, func.name, n.lineno,
                                      {fn} if fn else None, signer, n.func.id,
                                      sends_value))
        elif isinstance(n, ast.Tuple):
            elts = n.elts
            tg = [_target(e, consts) for e in elts]
            ab = [e.id for e in elts if isinstance(e, ast.Name) and e.id in abis]
            if any(tg) and ab and len(elts) >= 3 and isinstance(elts[2], ast.Constant):
                m.bindings.append(Binding(
                    next(t for t in tg if t), ab[0], func.name, n.lineno,
                    {elts[2].value}, "operator", "act_sequence step"))
        # (2) w3.eth.contract(address=<resolve(target)>, abi=<ABI>)
        if isinstance(n, ast.Call) and ast.unparse(n.func).endswith("eth.contract"):
            kw = {k.arg: k.value for k in n.keywords}
            abi_node, addr = kw.get("abi"), kw.get("address")
            if not isinstance(abi_node, ast.Name) or abi_node.id not in abis:
                continue
            targets: set = set()
            if isinstance(addr, ast.Call) and isinstance(addr.func, ast.Name) \
                    and addr.func.id in ("_resolve_system", "_resolve_component") \
                    and addr.args:
                a0 = addr.args[0]
                t = _target(a0, consts)
                if t:
                    targets = {t}
                elif isinstance(a0, ast.Name) and a0.id in local_targets:
                    targets = local_targets[a0.id]
            elif isinstance(addr, ast.Name) and addr.id == "WORLD_ADDRESS":
                targets = {"world"}
            if not targets:
                continue                     # classified by GENERIC_SITES
            var = _assigned_name(func, n)
            fns = _fn_attrs(func, var) if var else _chained_fns(n, func)
            for t in targets:
                m.bindings.append(Binding(t, abi_node.id, func.name, n.lineno,
                                          fns or None, "read", "eth.contract"))


def _parametric_helpers(funcs, abis) -> dict:
    """Functions that build `w3.eth.contract(address=_resolve_*(<param>),
    abi=<ABI constant>)` from one of their own parameters (send helpers
    excluded): {name: (param index, ABI, function names called)}."""
    out = {}
    for f in funcs:
        if f.name in SEND_HELPERS:
            continue
        params = [a.arg for a in f.args.args]
        for n in ast.walk(f):
            if not (isinstance(n, ast.Call)
                    and ast.unparse(n.func).endswith("eth.contract")):
                continue
            kw = {k.arg: k.value for k in n.keywords}
            addr, abi = kw.get("address"), kw.get("abi")
            if (isinstance(abi, ast.Name) and abi.id in abis
                    and isinstance(addr, ast.Call) and isinstance(addr.func, ast.Name)
                    and addr.func.id in ("_resolve_system", "_resolve_component")
                    and addr.args and isinstance(addr.args[0], ast.Name)
                    and addr.args[0].id in params):
                var = _assigned_name(f, n)
                fns = _fn_attrs(f, var) if var else _chained_fns(n, f)
                out[f.name] = (params.index(addr.args[0].id), abi.id, fns)
    return out


def _assigned_name(func, call) -> str | None:
    for n in ast.walk(func):
        if isinstance(n, ast.Assign) and n.value is call and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            return n.targets[0].id
    return None


def _chained_fns(call, func) -> set:
    out = set()
    for n in ast.walk(func):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Attribute)
                and n.value.attr == "functions" and n.value.value is call):
            out.add(n.attr)
    return out


def upstream() -> dict:
    return json.loads(UPSTREAM.read_text())


def upstream_fns(doc: dict, target: str) -> dict | None:
    if target == "world":
        return doc["abis"][doc["world"]["abi"]]
    for kind in ("systems", "components"):
        if target in doc[kind]:
            return doc["abis"][doc[kind][target]["abi"]]
    return None


def check(m: Model, doc: dict) -> list[str]:
    """Every bound ABI function must exist upstream on its target, with the
    same argument types and return types."""
    problems = []
    for name, std in STANDARD_ABIS.items():
        got = {signature(f): norm_outputs([_type(o) for o in f.get("outputs", [])])
               for f in m.abis.get(name, [])}
        if got != std:
            problems.append(f"{name} is {got}, not the standard {std}")
    for e in EXTRA_READS:
        up = upstream_fns(doc, e["target"]) or {}
        if e["signature"] not in up or norm_outputs(up[e["signature"]][1]) != e["outputs"]:
            problems.append(f"raw read {e['signature']} -> {e['outputs']} is not "
                            f"what {e['target']} has upstream")
    for e in EXTRA_WRITES:
        if e["target"] == "system.erc20.portal":
            if e["signature"] not in (upstream_fns(doc, e["target"]) or {}):
                problems.append(f"{e['signature']} is not on {e['target']} upstream")
    for b in m.bindings:
        up = upstream_fns(doc, b.target)
        if up is None:
            problems.append(f"{b.func}:{b.line}: {b.target} is not an upstream "
                            f"system or component")
            continue
        for fn in m.abis[b.abi]:
            if b.fns is not None and fn["name"] not in b.fns:
                continue
            sig = signature(fn)
            if sig not in up:
                problems.append(
                    f"{b.func}:{b.line}: {b.abi} encodes {sig} ({sel(sig)}) "
                    f"for {b.target}, which upstream does not have")
                continue
            if b.value and up[sig][2] != "payable":
                problems.append(
                    f"{b.func}:{b.line}: sends ETH to {sig} on {b.target}, "
                    f"which is {up[sig][2]} upstream")
            ours = norm_outputs([_type(o) for o in fn.get("outputs", [])])
            theirs = norm_outputs(up[sig][1])
            if ours != theirs:
                problems.append(
                    f"{b.func}:{b.line}: {b.abi}.{sig} returns {ours} here, "
                    f"{theirs} upstream ({b.target})")
        if b.fns:
            declared = {f["name"] for f in m.abis[b.abi]}
            for name in b.fns - declared:
                problems.append(f"{b.func}:{b.line}: {name} is not declared "
                                f"in {b.abi}")
    return problems


def tools_reaching(m: Model) -> dict:
    """function -> tools whose call closure includes it."""
    reach: dict[str, set] = {}
    for tool in m.tools:
        seen, stack = set(), [tool]
        while stack:
            f = stack.pop()
            if f in seen:
                continue
            seen.add(f)
            stack.extend(m.calls.get(f, ()))
        for f in seen:
            reach.setdefault(f, set()).add(tool)
    return reach


def build_table(m: Model, doc: dict) -> dict:
    """writes: one row per (tool, target, function) a tool can SEND, with
    its signer. reads: one row per (target, view function) any tool
    calls, with the tools that reach it."""
    reach = tools_reaching(m)
    writes: dict[tuple, dict] = {}
    reads: dict[tuple, dict] = {}
    dry: list[tuple] = []
    for b in m.bindings:
        up = upstream_fns(doc, b.target) or {}
        tools = sorted(reach.get(b.func, set())) or [f"({b.func})"]
        for fn in m.abis[b.abi]:
            if b.fns is not None and fn["name"] not in b.fns:
                continue
            sig = signature(fn)
            view = up.get(sig, [None, None, ""])[2] in ("view", "pure")
            if view:
                row = reads.setdefault((b.target, sig), {
                    "target": b.target, "signature": sig, "selector": sel(sig),
                    "returns": norm_outputs(up[sig][1]), "tools": set()})
                row["tools"].update(tools)
            elif b.signer == "read":
                # an eth_call of a write function: its dry-run. Tabled only
                # when no send of it is (listing every function of a
                # dynamically-dispatched contract would say nothing).
                if b.fns is not None:
                    dry.extend((t, b.target, sig) for t in tools)
            else:
                for tool in tools:
                    row = writes.setdefault((tool, b.target, sig), {
                        "tool": tool, "target": b.target, "signature": sig,
                        "selector": sel(sig), "signers": set()})
                    row["signers"].add(b.signer)
    for e in EXTRA_READS:
        row = reads.setdefault((e["target"], e["signature"]), {
            "target": e["target"], "signature": e["signature"],
            "selector": sel(e["signature"]), "returns": e["outputs"],
            "tools": set()})
        row["tools"].update(e["tools"])
    for e in EXTRA_WRITES:
        for tool in e["tools"]:
            writes[(tool, e["target"], e["signature"])] = {
                "tool": tool, "target": e["target"], "signature": e["signature"],
                "selector": None if e["signature"].startswith("(") else sel(e["signature"]),
                "signers": {e["signer"]}, "note": e["note"]}
    for key in dry:
        writes.setdefault(key, {"tool": key[0], "target": key[1],
                                "signature": key[2], "selector": sel(key[2]),
                                "signers": {"dry-run"}})

    out_w = []
    for key in sorted(writes):
        r = dict(writes[key])
        sg = sorted(r.pop("signers"))
        real = [x for x in sg if x != "dry-run"]
        r["signer"] = " / ".join(real) if real else "dry-run (eth_call) only"
        out_w.append(r)
    out_r = []
    for key in sorted(reads):
        r = dict(reads[key])
        r["tools"] = sorted(r["tools"])
        out_r.append(r)
    return {
        "provenance": {
            "upstream": doc["provenance"],
            "derived_from": "executor/server.py, statically "
                            "(tests/tools/encoding_table.py)",
        },
        "writes": out_w,
        "reads": out_r,
    }


if __name__ == "__main__":
    model = build_model()
    doc = upstream()
    bad = check(model, doc)
    for p in bad:
        print("MISMATCH", p)
    table = build_table(model, doc)
    if "--write" in sys.argv:
        TABLE.write_text(json.dumps(table, indent=1) + "\n")
        print(f"wrote {TABLE}: {len(table['writes'])} write rows, "
              f"{len(table['reads'])} read rows")
    else:
        print(json.dumps(table, indent=1)[:4000])
    sys.exit(1 if bad else 0)
