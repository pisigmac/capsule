"""Client configuration targets and path resolution."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class McpTarget:
    name: str
    config_path: Path
    root_key: str = "mcpServers"
    client_id: str = ""

    def __post_init__(self):
        if not self.client_id:
            self.client_id = self.name.lower().replace(" ", "_")

    @property
    def is_installed(self) -> bool:
        """Client is installed if its config file or config parent directory exists."""
        return self.config_path.exists() or self.config_path.parent.exists()


def get_system_targets() -> List[McpTarget]:
    """Resolve supported AI desktop clients for the current operating system."""
    sys_name = platform.system()
    home = Path.home()
    targets: List[McpTarget] = []

    # 1. Claude Desktop
    if sys_name == "Darwin":
        claude_path = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys_name == "Windows":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        claude_path = appdata / "Claude" / "claude_desktop_config.json"
    else:  # Linux / other
        claude_path = home / ".config" / "Claude" / "claude_desktop_config.json"

    targets.append(McpTarget(name="Claude Desktop", config_path=claude_path, client_id="claude"))

    # 2. Cursor IDE
    # Cursor supports ~/.cursor/mcp.json or GlobalStorage
    cursor_global = home / ".cursor" / "mcp.json"
    if sys_name == "Darwin":
        cursor_app_support = (
            home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json"
        )
    elif sys_name == "Windows":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        cursor_app_support = appdata / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json"
    else:
        cursor_app_support = home / ".config" / "Cursor" / "User" / "globalStorage" / "cursor.mcp" / "mcp.json"

    cursor_path = cursor_global if cursor_global.parent.exists() or not cursor_app_support.parent.exists() else cursor_app_support
    targets.append(McpTarget(name="Cursor", config_path=cursor_path, client_id="cursor"))

    # 3. Windsurf (Codeium)
    windsurf_path = home / ".codeium" / "windsurf" / "mcp_config.json"
    targets.append(McpTarget(name="Windsurf", config_path=windsurf_path, client_id="windsurf"))

    return targets
