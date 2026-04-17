"""Advisor MCP tool surface — per-request tool registry and handlers.

Plan 2026-04-17-003 Unit 9. Ada chat operates via named tools the model
invokes on demand; handlers run server-side with full Supabase creds,
user-scoped by JWT. Image bytes return as base64 content blocks — signed
URLs never enter the LLM payload or log stream.

The registry auto-discovers every ``tools_<feature>.py`` module so future
features (make-up, etc.) land by adding one file, with no adapter or
service changes.
"""

from app.advisor.mcp.context import McpContext
from app.advisor.mcp.registry import ToolRegistry

__all__ = ["McpContext", "ToolRegistry"]
