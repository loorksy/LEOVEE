"""Tools the agent can call: browse the data, look at the chart.

`LLMToolCall` existed on the provider protocol with nothing to dispatch it. This
is the registry and the dispatcher, and the same definitions are what the MCP
server exposes — one registry, two transports, one permission model, so a tool
cannot behave differently depending on which door it came through.
"""

from app.agents.tools.registry import (
    TOOLS,
    ToolContext,
    ToolSpec,
    dispatch_tool,
    tool_definitions,
)

__all__ = ["TOOLS", "ToolContext", "ToolSpec", "dispatch_tool", "tool_definitions"]
