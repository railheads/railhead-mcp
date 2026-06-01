"""Offline smoke tests for MCPAgent — no chain, no real MCP server required.

Verifies the result-coercion logic, the runtime's async/sync bridge primitive
shapes, and the agent-side binding of fake tools to capabilities.

Run directly:    python tests/test_wrapper.py
Run via pytest:  pytest tests/
"""
from types import SimpleNamespace

from railhead_mcp import MCPAgent, __version__
from railhead_mcp.wrapper import _coerce_tool_result


# ── Fakes for tests that don't need a real MCP server ──

class _FakeMessage:
    def __init__(self, text):
        self.text = text


class _FakeResult:
    def __init__(self, content, is_error=False):
        self.content = content
        self.isError = is_error


def _bare_agent() -> MCPAgent:
    """Build an MCPAgent without a chain or any MCP runtime."""
    agent = MCPAgent.__new__(MCPAgent)
    agent._handlers = {}
    agent._last_block = 0
    agent._api_url = ""
    agent._mcp_runtimes = []
    return agent


# ── Tests ──

def test_version_string():
    assert isinstance(__version__, str) and __version__.count(".") >= 1


def test_coerce_single_text_block():
    result = _FakeResult([_FakeMessage("hello world")])
    assert _coerce_tool_result(result) == {"text": "hello world"}


def test_coerce_error_with_text_block():
    result = _FakeResult([_FakeMessage("file not found")], is_error=True)
    assert _coerce_tool_result(result) == {"error": "file not found"}


def test_coerce_error_with_no_content():
    result = _FakeResult([], is_error=True)
    assert _coerce_tool_result(result) == {"error": "(unknown MCP tool error)"}


def test_coerce_multiple_text_blocks_returns_content_list():
    result = _FakeResult([_FakeMessage("a"), _FakeMessage("b")])
    out = _coerce_tool_result(result)
    assert out == {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}


def test_coerce_non_text_block():
    class _Blob:
        pass
    result = _FakeResult([_Blob()])
    out = _coerce_tool_result(result)
    assert "content" in out
    assert out["content"][0]["type"] == "_Blob"


def test_bind_attaches_handler():
    class _StubRuntime:
        def call_tool(self, name, args, timeout=120):
            return _FakeResult([_FakeMessage(f"ran {name}({args})")])

    agent = _bare_agent()
    agent._bind("test_cap", _StubRuntime(), "demo_tool")
    assert "test_cap" in agent._handlers


def test_bound_handler_calls_through_to_runtime():
    seen: dict = {}

    class _StubRuntime:
        def call_tool(self, name, args, timeout=120):
            seen["name"] = name
            seen["args"] = args
            return _FakeResult([_FakeMessage("ok")])

    agent = _bare_agent()
    agent._bind("test_cap", _StubRuntime(), "demo_tool")
    result = agent._handlers["test_cap"](SimpleNamespace(input={"x": 1}))
    assert seen == {"name": "demo_tool", "args": {"x": 1}}
    assert result == {"text": "ok"}


def test_bound_handler_passes_empty_dict_for_non_dict_input():
    """If job.input is somehow not a dict, fall back to {} so the MCP call
    still gets a valid arguments shape rather than choking on None or a list."""
    seen: dict = {}

    class _StubRuntime:
        def call_tool(self, name, args, timeout=120):
            seen["args"] = args
            return _FakeResult([_FakeMessage("ok")])

    agent = _bare_agent()
    agent._bind("test_cap", _StubRuntime(), "demo_tool")
    agent._handlers["test_cap"](SimpleNamespace(input=None))
    assert seen["args"] == {}


def test_inherits_railhead_agent_handlers_dict():
    """MCPAgent shares _handlers semantics with RailheadAgent so on() still works."""
    agent = _bare_agent()
    # The decorator-style register from the base class:
    @agent.on("custom_cap")
    def _handle(job):
        return {"echoed": job.input.get("msg")}
    assert "custom_cap" in agent._handlers


if __name__ == "__main__":
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
