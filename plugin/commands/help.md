---
name: help
description: Show available commands for this app
---

# Help

Display all available commands and their descriptions.

## Steps

1. List all commands in the plugin's `commands/` directory
2. Present them in a formatted table:

| Command | Description |
|---------|-------------|
| /help | Show this help message |

3. Include a note about the MCP tools available via the server:

> "This app also exposes MCP tools. Use the tool discovery endpoint at `/api/v1/docs/tools` to see all available tools, or connect directly via MCP at `/mcp`."
