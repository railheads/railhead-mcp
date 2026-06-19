"""JSON Schema MCP demo: expose one safe MCP tool as a Railhead capability.

Local one-shot:
  python examples/json_schema_agent.py --once

Serve on Railhead after `railhead init --invite-code ...`:
  python examples/json_schema_agent.py --serve
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from mcp import StdioServerParameters
from railhead_mcp import MCPAgent


CAPABILITY = "json_schema_check"
SERVER_PATH = Path(__file__).with_name("json_schema_server.py")
SAMPLE_INPUT = {
    "instance": {
        "symbol": "BTC",
        "confidence": 0.72,
        "direction": "long",
    },
    "schema": {
        "type": "object",
        "required": ["symbol", "confidence", "direction"],
        "properties": {
            "symbol": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "direction": {"type": "string", "enum": ["long", "short", "neutral"]},
        },
        "additionalProperties": False,
    },
}


def server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )


def build_agent() -> MCPAgent:
    agent = MCPAgent.from_credentials()
    agent.serve_mcp_tool(
        capability=CAPABILITY,
        server_params=server_params(),
        tool_name=CAPABILITY,
    )
    return agent


def run_once() -> None:
    agent = MCPAgent.__new__(MCPAgent)
    agent._handlers = {}
    agent._last_block = 0
    agent._api_url = ""
    agent._mcp_runtimes = []
    agent.serve_mcp_tool(
        capability=CAPABILITY,
        server_params=server_params(),
        tool_name=CAPABILITY,
    )
    try:
        result = agent._handlers[CAPABILITY](type("Job", (), {"input": SAMPLE_INPUT})())
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        for runtime in agent._mcp_runtimes:
            runtime.stop()


def serve(price_rail: float, stake_rail: float, poll_secs: float) -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
    agent = build_agent()
    agent.run(
        price_rail=price_rail,
        stake_rail=stake_rail,
        endpoint="polling",
        poll_secs=poll_secs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run a local one-shot demo.")
    mode.add_argument("--serve", action="store_true", help="Serve json_schema_check on Railhead.")
    parser.add_argument("--price-rail", type=float, default=1.0)
    parser.add_argument("--stake-rail", type=float, default=1000.0)
    parser.add_argument("--poll-secs", type=float, default=5.0)
    args = parser.parse_args()

    if args.serve:
        serve(args.price_rail, args.stake_rail, args.poll_secs)
    else:
        run_once()


if __name__ == "__main__":
    main()
