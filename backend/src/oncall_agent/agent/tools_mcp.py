"""DataHub MCP server construction and fault-tolerant manager lifecycle."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from agents.mcp import MCPServerManager, MCPServerStdio, create_static_tool_filter

from oncall_agent.config import Settings, get_settings


def _is_writable(path: Path) -> bool:
    """Return whether ``path`` (or the nearest existing ancestor) can be written to."""

    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return os.access(probe, os.W_OK)

MCP_TOOL_NAMES = [
    "search",
    "get_entities",
    "get_lineage",
    "get_lineage_paths_between",
    "list_schema_fields",
    "get_dataset_queries",
]


def build_datahub_mcp_server(settings: Settings | None = None) -> MCPServerStdio:
    """Build the pinned, read-only DataHub stdio MCP server."""

    resolved = settings or get_settings()
    environment = dict(os.environ)
    environment.pop("DATAHUB_GMS_TOKEN", None)
    environment.update(
        {
            "DATAHUB_GMS_URL": resolved.datahub_gms_url,
            # Without this every MCP tool call can block ~54s on a synchronous telemetry ping
            # (acryldata/mcp-server-datahub#152). It is the highest-impact line in this file.
            "DATAHUB_TELEMETRY_ENABLED": "false",
            "LOGURU_LEVEL": "WARNING",
        }
    )
    if "UV_TOOL_DIR" not in environment:
        # uvx stages the pinned server under ~/.local/share/uv, which is unwritable in some
        # sandboxes. Fall back to a temp dir only when the default is not usable, so a normal
        # machine keeps its shared uv tool cache instead of re-downloading every launch.
        default_tool_dir = Path(
            environment.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        ) / "uv"
        if not _is_writable(default_tool_dir):
            environment["UV_TOOL_DIR"] = str(Path(tempfile.gettempdir()) / "oncall-uv-tools")
    return MCPServerStdio(
        name="datahub",
        params={
            "command": shutil.which("uvx") or "uvx",
            "args": ["mcp-server-datahub@0.6.0"],
            "env": environment,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        max_retry_attempts=2,
        tool_filter=create_static_tool_filter(allowed_tool_names=MCP_TOOL_NAMES),
    )


def build_mcp_manager(settings: Settings | None = None) -> MCPServerManager:
    """Return a manager that drops a failed DataHub server instead of aborting startup."""

    return MCPServerManager(
        [build_datahub_mcp_server(settings)],
        drop_failed_servers=True,
        connect_timeout_seconds=45,
    )
