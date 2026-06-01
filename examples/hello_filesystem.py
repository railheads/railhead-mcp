"""Hello world: serve the entire MCP filesystem server as Railhead capabilities.

Prereqs:
  - You've run `railhead init --invite-code XXX` so ~/.railhead/config.json exists
    with a funded wallet on Chain 7777.
  - Node + npm available (this example uses `npx` to spawn the official
    @modelcontextprotocol/server-filesystem server).
  - `pip install railhead-mcp`

The filesystem MCP server scopes file access to a single root directory. The
example uses /tmp/railhead-mcp-demo; change it to whatever you like.

Run it:
  python hello_filesystem.py

Every tool the server exposes (read_file, write_file, list_directory, ...)
becomes a Railhead capability prefixed with "fs_". Clients then post jobs
to capabilities like "fs_read_file" and the wrapper invokes the MCP tool
with their input.
"""
import logging
import os
from pathlib import Path

from mcp import StdioServerParameters
from railhead_mcp import MCPAgent

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

ROOT = Path("/tmp/railhead-mcp-demo")
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / "hello.txt").write_text("hello from the railhead mcp demo\n")

server = StdioServerParameters(
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", str(ROOT)],
)

agent = MCPAgent.from_credentials()
agent.serve_mcp_server(server, capability_prefix="fs_")
agent.run(price_rail=1, stake_rail=1000)


# ── Wrap a single specific tool instead (alternative pattern) ──
#
# agent.serve_mcp_tool(
#     capability="read_my_files",
#     server_params=server,
#     tool_name="read_file",
# )
