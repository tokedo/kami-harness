"""Environment-interface schema version for the Kamigotchi MCP server.

This version identifies the *contract* that KamiBench agents build
against: the set of MCP tools, their parameters, and their semantics.

Bumped per the semver policy in the repo-root CHANGELOG.md:
  MAJOR — breaking change to an existing tool's name, params, or semantics
  MINOR — new tools or new optional params (additive)
  PATCH — doc fixes, non-semantic changes

It is surfaced to clients two ways:
  1. As the MCP ``server_version`` in the initialize handshake (set in
     server.py on the FastMCP low-level server).
  2. As this importable constant, for tests and downstream tooling.
"""

SCHEMA_VERSION = "1.0.0"
