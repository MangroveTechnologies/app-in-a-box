# Contributing

Guide for extending the scaffold — adding endpoints, services, and MCP tools on top of what ships.

## Service layer pattern

Routes (`server/src/api/routes/`) and MCP tools (`server/src/mcp/tools.py`) both call shared services in `server/src/services/`. Never duplicate business logic — if the same capability needs to be reachable from both REST and MCP, it lives in a service and both call in.

## Adding a free endpoint

1. Create the route in `server/src/api/routes/{resource}.py`.
2. Create the service in `server/src/services/{resource}.py`.
3. Register the route in `server/src/api/router.py` under `api_router`.
4. Register the MCP tool in `server/src/mcp/tools.py` via `register_tool()`.
5. Write tests in `server/tests/test_{resource}.py`, mirroring the `src/` structure.

## Adding an auth-gated endpoint

Same five steps, plus:

- Call `validate_api_key()` in the route handler.
- Call `has_valid_api_key()` in the MCP tool before proceeding.

## Adding an x402 payment-gated endpoint

Register the route under `x402_router` (not `api_router`). See `server/src/api/routes/hello_mangrove.py` for the canonical pattern.

## Testing

Tests live in `server/tests/` and mirror the `src/` layout. CI (`.github/workflows/ci.yml`) runs ruff + pytest on every PR — that's the authoritative invocation.

Test runs set `MASTER_KEY_PATH` to a test-scoped path; the resulting `agent-data-test/` directory is gitignored.

## Git workflow

See `.claude/rules/git-workflow.md`. Feature branch off `main`, one concern per PR, CI must pass.
