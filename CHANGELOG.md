# Changelog

All notable changes to Railhead MCP are tracked here.

## 0.1.0 - Builder Preview

Release status: prepared for GitHub source install. PyPI publication is not yet
confirmed.

### Added

- Initial wrapper package for serving MCP tools as Railhead-paid agent capabilities.
- GitHub-based dependency on the Railhead Python SDK while the SDK is not yet on
  PyPI.
- Example and README guidance for invite-code onboarding via `railhead init`.
- Provider-neutral `json_schema_check` MCP demo server and Railhead agent example with no network, filesystem, or shell access.
- Structured JSON-object text coercion for MCP servers that return JSON through text content blocks.

### Changed

- Agent run examples default to `endpoint="polling"` to match Railhead alpha job
  delivery.
- README now leads with the safe `json_schema_check` demo and uses Builder Preview wording.
