"""Vendor the upstream game ABIs the static encoding test checks against.

Usage (from executor/):

    python3 tests/tools/vendor_upstream_abi.py <path to a kamigotchi checkout>

The checkout must be at UPSTREAM_COMMIT; the script refuses any other
commit, so the fixture's provenance line is always true. It reads, for
every system and component, its id from the Solidity source
(`uint256 constant ID = uint256(keccak256("<id>"))`) and the contract's
compiled ABI from `packages/client/abi/<Contract>.json`, plus the World
contract, and writes `tests/fixtures/upstream_abi/upstream_abi.json`:

    provenance: repository, commit, inputs, generator
    abis:       {abi_hash: {signature: [selector, outputs, mutability]}}
    systems:    {system_id: {contract, source, abi}}
    components: {component_id: {contract, source, abi}}
    world:      {contract, abi}

Only functions are kept (no events or errors); an ABI shared by many
contracts (most components) is stored once, under its hash.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from eth_utils import keccak

UPSTREAM_REPOSITORY = "https://github.com/Asphodel-OS/kamigotchi"
UPSTREAM_COMMIT = "ffda396330af1bc33238b6c37188772152b45439"
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "upstream_abi" / "upstream_abi.json"

_ID = re.compile(r'uint256\s+constant\s+ID\s*=\s*uint256\(keccak256\("([^"]+)"\)\)')
_CONTRACT = re.compile(r"^contract\s+(\w+)\s+is\b", re.M)


def _type(p: dict) -> str:
    """Canonical ABI type, tuples expanded (as the selector hashes them)."""
    t = p["type"]
    if t.startswith("tuple"):
        inner = ",".join(_type(c) for c in p.get("components", []))
        return f"({inner}){t[len('tuple'):]}"
    return t


def _functions(abi: list) -> dict:
    out = {}
    for e in abi:
        if e.get("type") != "function":
            continue
        sig = f"{e['name']}({','.join(_type(i) for i in e.get('inputs', []))})"
        out[sig] = [
            "0x" + keccak(text=sig)[:4].hex(),
            [_type(o) for o in e.get("outputs", [])],
            e.get("stateMutability", ""),
        ]
    return dict(sorted(out.items()))


def _load_abi(abi_dir: Path, contract: str) -> list:
    raw = json.loads((abi_dir / f"{contract}.json").read_text())
    return raw["abi"] if isinstance(raw, dict) else raw


def main(root: str) -> None:
    repo = Path(root)
    head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != UPSTREAM_COMMIT:
        sys.exit(f"checkout is at {head}, not {UPSTREAM_COMMIT}")
    src = repo / "packages" / "contracts" / "src"
    abi_dir = repo / "packages" / "client" / "abi"
    abis: dict[str, dict] = {}

    def intern(fns: dict) -> str:
        h = hashlib.sha256(json.dumps(fns, sort_keys=True).encode()).hexdigest()[:16]
        abis[h] = fns
        return h

    tables: dict[str, dict] = {"systems": {}, "components": {}}
    for kind in ("systems", "components"):
        for sol in sorted((src / kind).rglob("*.sol")):
            text = sol.read_text()
            ids, names = _ID.findall(text), _CONTRACT.findall(text)
            if len(ids) != 1 or len(names) != 1:
                sys.exit(f"{sol}: expected one ID and one contract, got {ids} {names}")
            tables[kind][ids[0]] = {
                "contract": names[0],
                "source": str(sol.relative_to(repo)),
                "abi": intern(_functions(_load_abi(abi_dir, names[0]))),
            }
    doc = {
        "provenance": {
            "repository": UPSTREAM_REPOSITORY,
            "commit": UPSTREAM_COMMIT,
            "inputs": "packages/contracts/src/{systems,components}/**/*.sol "
                      "(ids) + packages/client/abi/<Contract>.json (ABIs)",
            "generator": "executor/tests/tools/vendor_upstream_abi.py",
        },
        "abis": dict(sorted(abis.items())),
        "systems": dict(sorted(tables["systems"].items())),
        "components": dict(sorted(tables["components"].items())),
        "world": {"contract": "World",
                  "abi": intern(_functions(_load_abi(abi_dir, "World")))},
    }
    doc["abis"] = dict(sorted(abis.items()))
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n")
    print(f"wrote {OUT}: {len(doc['systems'])} systems, "
          f"{len(doc['components'])} components, {len(abis)} distinct ABIs")


if __name__ == "__main__":
    main(sys.argv[1])
