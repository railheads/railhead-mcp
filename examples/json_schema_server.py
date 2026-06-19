"""Local MCP server exposing a safe JSON Schema validation tool.

This server is intentionally local-only and deterministic: no network, no file
access, no shell access. It exists as the first polished Railhead MCP demo tool.
"""
from __future__ import annotations

from time import perf_counter
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("railhead-json-schema")


@mcp.tool()
def json_schema_check(instance: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Validate a JSON object against a JSON Schema.

    Returns a deterministic structured result with validity, error details, and
    latency metadata. The tool does not read files, call networks, or execute
    code.
    """
    started = perf_counter()
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.path))
    except SchemaError as exc:
        return {
            "capability": "json_schema_check",
            "valid": False,
            "schema_valid": False,
            "errors": [
                {
                    "path": [],
                    "message": f"Invalid schema: {exc.message}",
                    "validator": exc.validator,
                }
            ],
            "performance": _performance(started),
        }

    return {
        "capability": "json_schema_check",
        "valid": not errors,
        "schema_valid": True,
        "errors": [
            {
                "path": list(error.path),
                "message": error.message,
                "validator": error.validator,
            }
            for error in errors[:20]
        ],
        "performance": _performance(started),
    }


def _performance(started: float) -> dict[str, Any]:
    return {
        "latency_ms": round((perf_counter() - started) * 1000, 3),
        "engine": "railhead-mcp-json-schema-local-v0",
        "external_calls": 0,
    }


if __name__ == "__main__":
    mcp.run()
