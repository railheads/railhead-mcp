"""MCPAgent — bind MCP (Model Context Protocol) tools to Railhead capabilities.

An MCP server exposes one or more tools, each with a declared input schema and
a structured output. That maps almost 1:1 to a Railhead capability — same idea
of "do one thing well, with a typed contract." This wrapper:

  - Spawns the MCP server as a persistent subprocess on agent startup.
  - Runs an asyncio event loop in a background thread (MCP is async, Railhead
    handlers are sync — we bridge with ``run_coroutine_threadsafe``).
  - Exposes either one specific tool, or every tool the server provides, as
    Railhead capabilities.

Quick start::

    from mcp import StdioServerParameters
    from railhead_mcp import MCPAgent

    params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp/railhead-demo"],
    )

    agent = MCPAgent.from_credentials()
    agent.serve_mcp_server(params, capability_prefix="fs_")
    agent.run(price_rail=1, stake_rail=1000)

Every tool the MCP server exposes becomes a hireable Railhead capability with
the tag ``fs_<tool_name>`` (e.g. ``fs_read_file``, ``fs_list_directory``).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, Iterable

from mcp import ClientSession, StdioServerParameters, stdio_client
from railhead import RailheadAgent

log = logging.getLogger("railhead_mcp")


# ── Async/sync bridge ─────────────────────────────────────────────────────────

class _MCPRuntime:
    """Owns one MCP subprocess + its asyncio event loop, on a background thread.

    The Railhead handler is sync; MCP is async. We keep the server running for
    the lifetime of the agent, so each handler call is just a ``call_tool``
    coroutine submitted to this runtime's loop — no per-call subprocess spawn.
    """

    def __init__(self, server_params: StdioServerParameters, ready_timeout: float = 30.0):
        self._params = server_params
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self._tools_cache: list[Any] = []
        self._ready = threading.Event()
        self._error: Exception | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._thread_target,
            name=f"mcp-runtime-{server_params.command[:20]}",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=ready_timeout):
            raise TimeoutError(
                f"MCP runtime did not become ready within {ready_timeout}s. "
                f"Is the server command valid? command={server_params.command!r}"
            )
        if self._error:
            raise RuntimeError(f"MCP runtime failed to start: {self._error}") from self._error

    def _thread_target(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception as e:
            self._error = e
            self._ready.set()  # unblock waiter so the constructor can raise

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        async with stdio_client(self._params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                self._session = session
                tools_result = await session.list_tools()
                self._tools_cache = list(tools_result.tools)
                self._ready.set()
                # Park the loop until stop() is called.
                while not self._stop.is_set():
                    await asyncio.sleep(0.5)

    # ── Sync API the wrapper calls into ──

    @property
    def tools(self) -> list[Any]:
        return self._tools_cache

    def call_tool(self, name: str, arguments: dict, timeout: float = 120.0) -> Any:
        if self._session is None or self._loop is None:
            raise RuntimeError("MCP runtime is not initialized.")
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, arguments),
            self._loop,
        )
        return fut.result(timeout=timeout)

    def stop(self) -> None:
        self._stop.set()


# ── Result coercion ───────────────────────────────────────────────────────────

def _coerce_tool_result(result: Any) -> dict:
    """Turn an MCP CallToolResult into a Railhead result dict.

    Handles the common content shapes:
      - error result        → {"error": "<text>"}
      - single text block   → {"text": "<text>"}
      - multiple blocks     → {"content": [{"type": "...", ...}, ...]}
    """
    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    content = getattr(result, "content", []) or []

    if is_error:
        msg = ""
        for block in content:
            text = getattr(block, "text", None)
            if text:
                msg = text
                break
        return {"error": msg or "(unknown MCP tool error)"}

    if len(content) == 1:
        only = content[0]
        text = getattr(only, "text", None)
        if isinstance(text, str):
            return {"text": text}

    out = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            out.append({"type": "text", "text": text})
        else:
            out.append({"type": type(block).__name__, "data": str(block)})
    return {"content": out}


# ── The agent ─────────────────────────────────────────────────────────────────

class MCPAgent(RailheadAgent):
    """A Railhead agent backed by Model Context Protocol tools.

    Subclasses ``RailheadAgent``; you keep every method you already know
    (``.run()``, ``.register()``, ``.from_credentials()``, etc.) and gain two
    new ones for binding MCP tools.

    Quick start in the module docstring above.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mcp_runtimes: list[_MCPRuntime] = []

    @classmethod
    def from_api(cls, api_url: str, private_key: str) -> "MCPAgent":
        inst = super().from_api(api_url, private_key)
        inst._mcp_runtimes = []
        return inst

    @classmethod
    def from_credentials(cls, config_path: str | None = None) -> "MCPAgent":
        inst = super().from_credentials(config_path)
        inst._mcp_runtimes = []
        return inst

    # ── Tool binding ──

    def serve_mcp_tool(
        self,
        capability: str,
        server_params: StdioServerParameters,
        tool_name: str,
    ) -> None:
        """Bind a single tool from an MCP server to a single Railhead capability."""
        runtime = _MCPRuntime(server_params)
        names = [t.name for t in runtime.tools]
        if tool_name not in names:
            runtime.stop()
            raise ValueError(
                f"MCP server does not expose a tool named {tool_name!r}. "
                f"Available tools: {names}"
            )
        self._bind(capability, runtime, tool_name)
        self._mcp_runtimes.append(runtime)
        log.info("Bound MCP tool '%s' to Railhead capability '%s'", tool_name, capability)

    def serve_mcp_server(
        self,
        server_params: StdioServerParameters,
        capability_prefix: str = "",
        only: Iterable[str] | None = None,
    ) -> None:
        """Bind every tool the MCP server provides as a separate Railhead capability.

        :param server_params:     How to spawn the MCP server (stdio subprocess).
        :param capability_prefix: Prepended to every tool name when registering as a
                                  capability (e.g. ``"fs_"`` → ``fs_read_file``).
        :param only:              Optional iterable of tool names to expose; others
                                  are silently skipped. Defaults to all tools.
        """
        runtime = _MCPRuntime(server_params)
        allow = set(only) if only is not None else None
        bound: list[str] = []
        for tool in runtime.tools:
            if allow is not None and tool.name not in allow:
                continue
            cap = f"{capability_prefix}{tool.name}" if capability_prefix else tool.name
            self._bind(cap, runtime, tool.name)
            bound.append(cap)
        self._mcp_runtimes.append(runtime)
        log.info("Bound %d MCP tools as Railhead capabilities: %s", len(bound), bound)

    def _bind(self, capability: str, runtime: _MCPRuntime, tool_name: str) -> None:
        def handler(job):
            args = job.input if isinstance(job.input, dict) else {}
            result = runtime.call_tool(tool_name, args)
            return _coerce_tool_result(result)

        handler.__name__ = f"{capability}_mcp_handler"
        self._handlers[capability] = handler

    # ── Lifecycle ──

    def run(
        self,
        price_rail: float | None = None,
        stake_rail: float = 1000.0,
        endpoint: str = "",
        poll_secs: float = 5.0,
    ) -> None:
        """Start the agent's poll loop.

        If ``price_rail`` is provided, every capability bound via
        ``serve_mcp_tool()`` / ``serve_mcp_server()`` is registered on-chain
        first (a no-op if the agent is already registered). Otherwise this
        just polls — useful if you registered separately.
        """
        if price_rail is not None:
            caps = list(self._handlers.keys())
            if not caps:
                raise RuntimeError(
                    "No capabilities bound. Call .serve_mcp_tool(...) or "
                    ".serve_mcp_server(...) before .run()."
                )
            self.register(
                capabilities=caps,
                price_rail=price_rail,
                stake_rail=stake_rail,
                endpoint=endpoint,
            )
        super().run(poll_secs=poll_secs)
