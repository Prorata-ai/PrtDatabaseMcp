"""Entry: stdio (Cursor) or HTTP (cloud)."""

import argparse
import sys
from pathlib import Path

try:
    from prt_mcp_common.transport import add_transport_args, run_server
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "PrtMcpCommon" / "src"))
    from prt_mcp_common.transport import add_transport_args, run_server

from .server import create_server, readiness_check


def main() -> None:
    parser = argparse.ArgumentParser(description="ProRata PostgreSQL MCP server")
    add_transport_args(parser)
    args = parser.parse_args()
    mcp_server = create_server()
    run_server(mcp_server, args, readiness_check=readiness_check)


if __name__ == "__main__":
    main()
