"""Real stdio MCP handshake/tools. Run in the Codex tool container."""

import sys
import unittest
from pathlib import Path

if not Path("/run/secrets/codex-asante.env").is_file():
    raise unittest.SkipTest("Run the dedicated Codex mcp-verify check with read-only credentials")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scripts.codex.settings import TOOLS


class CodexMcpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mcp_session_has_only_readonly_tools_and_authenticated_reads(self):
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "scripts.codex.project_mcp"],
        )
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                listing = await session.list_tools()
                self.assertEqual({tool.name for tool in listing.tools}, set(TOOLS))
                for tool in listing.tools:
                    self.assertTrue(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.destructiveHint)
                for name, arguments in [
                    ("codex_asante_db_status", {}),
                    ("codex_asante_db_tables", {"limit": 5}),
                    ("codex_asante_db_table_info", {"table": "spatial_ref_sys"}),
                    ("codex_asante_db_spatial_reference", {"srid": 4326}),
                    ("codex_asante_minio_status", {}),
                    ("codex_asante_minio_objects", {"limit": 5}),
                ]:
                    result = await session.call_tool(name, arguments)
                    self.assertFalse(result.isError, name)
                invalid = await session.call_tool("codex_asante_db_table_info", {"table": "x; DROP TABLE x"})
                self.assertTrue(invalid.isError)


if __name__ == "__main__":
    unittest.main()
