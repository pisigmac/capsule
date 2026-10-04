"""Capsule MCP client installer module."""
from .mcp_installer import McpInstaller, McpTarget, detect_installed_clients, resolve_caps_command
from .targets import get_system_targets

__all__ = [
    "McpInstaller",
    "McpTarget",
    "detect_installed_clients",
    "resolve_caps_command",
    "get_system_targets",
]
