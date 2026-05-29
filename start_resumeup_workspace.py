#!/usr/bin/env python3
"""Helper to launch the ResumeUp MCP server for local LLM clients."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def build_mcp_config(server_path: Path) -> dict:
    """Build a Cursor/Claude Desktop MCP config snippet."""
    return {
        "mcpServers": {
            "resumeup": {
                "command": sys.executable,
                "args": [str(server_path)],
                "env": {
                    "RESUMEUP_HEADLESS": "false",
                },
            }
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Start or configure the ResumeUp MCP server.")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print MCP client configuration JSON and exit",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent
    server_path = repo_root / "mcp_server.py"

    if args.print_config:
        print(json.dumps(build_mcp_config(server_path), indent=2))
        return

    subprocess.run([sys.executable, str(server_path)], check=False)


if __name__ == "__main__":
    main()
