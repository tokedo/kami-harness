"""Checks on the repo-root contract registry (SPEC.md).

Cheap structural checks only: the file exists, its frontmatter is
well-formed, and its `describes:` names a ref that actually resolves in
this repository. The claims *inside* SPEC.md are enforced by the tests
it cites, not here.
"""

import re
import subprocess
from pathlib import Path

import pytest

import server

SPEC_PATH = Path(server._REPO) / "SPEC.md"

REQUIRED_SECTIONS = (
    "## Provides",
    "## Depends",
    "## Invariants",
    "## Deliberate deviations",
    "## Non-goals",
    "## Changelog",
)


def _frontmatter() -> dict:
    text = SPEC_PATH.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SPEC.md must open with a --- fenced frontmatter block"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_spec_exists():
    assert SPEC_PATH.is_file(), f"missing contract registry: {SPEC_PATH}"


def test_spec_frontmatter():
    fm = _frontmatter()
    assert fm.get("module") == "kami-harness"
    assert re.fullmatch(r"\d+", fm.get("version", "")), fm.get("version")
    assert fm.get("describes"), "frontmatter needs a describes: ref"


def test_spec_has_all_sections():
    text = SPEC_PATH.read_text()
    for heading in REQUIRED_SECTIONS:
        assert re.search(rf"^{re.escape(heading)}\s*$", text, re.M), heading


def test_invariant_rows_all_carry_enforcement():
    """Every row of the Invariants table has a non-empty enforcement
    cell. `unenforced` is legal and visible; empty is not."""
    text = SPEC_PATH.read_text()
    body = text.split("## Invariants", 1)[1].split("\n---", 1)[0]
    rows = [
        r for r in re.findall(r"^\|(.+)\|$", body, re.M)
        if not re.fullmatch(r"[\s|:-]+", r)
    ]
    rows = [r for r in rows if r.split("|")[0].strip().lower() != "claim"]
    assert rows, "Invariants table has no rows"
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        assert len(cells) == 2, f"expected claim|enforcement, got: {row}"
        assert cells[0], f"empty claim in row: {row}"
        assert cells[1], f"empty enforcement in row: {row}"


def test_describes_resolves():
    """The ref named in `describes:` exists in this repository, and when
    the line carries both a tag and a short sha they agree."""
    describes = _frontmatter()["describes"]
    refs = re.findall(r"[\w.\-/]+", describes)
    assert refs, f"no ref token in describes: {describes!r}"

    def rev_parse(ref):
        r = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=str(server._REPO), capture_output=True, text=True,
        )
        return r.stdout.strip() if r.returncode == 0 else None

    if rev_parse("HEAD") is None:
        pytest.skip("not a git repository")

    resolved = {ref: rev_parse(ref) for ref in refs}
    unresolved = [ref for ref, sha in resolved.items() if sha is None]
    assert not unresolved, (
        f"describes: names ref(s) that do not resolve: {unresolved}"
    )
    shas = set(resolved.values())
    assert len(shas) == 1, (
        f"describes: names refs pointing at different commits: {resolved}"
    )
