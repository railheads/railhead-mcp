# Railhead MCP Release Checklist

Use this checklist before syncing or publishing `railhead-mcp`.

## Versioning

- Update `railhead_mcp/__init__.py#__version__`.
- Confirm `pyproject.toml` uses the dynamic version from `railhead_mcp.__version__`.
- Update `CHANGELOG.md` with notable changes.

## Safety Gates

- Do not commit private keys, tokens, or local credential files.
- Confirm current refs contain no 64-hex secret-shaped values.
- Confirm dependency points at the intended Railhead SDK source or published
  package.

## Local Verification

```bash
python -m compileall railhead_mcp
python -m pytest
python -m build
```

## Public Sync

- Push to `railheads/railhead-mcp` only after local tests pass.
- Confirm README install instructions match the current publication channel.
