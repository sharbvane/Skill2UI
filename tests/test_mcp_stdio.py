"""Real JSON-RPC round-trip through an official MCP client and stdio process."""
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from skill2ui import __version__


PROJECT = Path(__file__).resolve().parents[1]
RESOURCE = "ui://skill2ui/app.html"


class MCPStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_tools_resource_and_invalid_schema(self):
        with tempfile.TemporaryDirectory(prefix="skill2ui-mcp-stdio-") as directory:
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "skill2ui", "mcp", "--data-dir", directory],
                cwd=PROJECT,
                env={"PYTHONUTF8": "1"},
            )
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as client:
                    initialized = await client.initialize()
                    self.assertEqual(initialized.serverInfo.version, __version__)
                    tools = (await client.list_tools()).tools
                    by_name = {tool.name: tool for tool in tools}
                    self.assertEqual(set(by_name), {"skill2ui_generate", "skill2ui_evaluate", "skill2ui_inspect"})
                    self.assertEqual(by_name["skill2ui_generate"].meta["ui"]["resourceUri"], RESOURCE)
                    self.assertEqual(by_name["skill2ui_evaluate"].meta["ui"]["visibility"], ["app"])
                    resources = (await client.list_resources()).resources
                    resource = next(item for item in resources if str(item.uri) == RESOURCE)
                    self.assertEqual(resource.mimeType, "text/html;profile=mcp-app")
                    self.assertEqual(resource.meta["ui"]["csp"], {"connectDomains": [], "resourceDomains": []})
                    html = (await client.read_resource(RESOURCE)).contents[0].text
                    self.assertIn("<!doctype html>", html)
                    self.assertIn('<script type="module">', html)
                    self.assertNotIn('src="http', html)
                    generated = await client.call_tool("skill2ui_generate", {"prompt": "AA费用计算器"})
                    self.assertFalse(generated.isError)
                    document = generated.structuredContent["document"]
                    self.assertEqual(document["kind"], "calculator")
                    evaluated = await client.call_tool("skill2ui_evaluate", {
                        "document": document, "state": {"total": 900, "people": 3, "tip": 20},
                    })
                    self.assertFalse(evaluated.isError)
                    self.assertEqual(evaluated.structuredContent["metrics"]["per_person"], 360)
                    inspected = await client.call_tool("skill2ui_inspect", {
                        "path": str(PROJECT / "examples/third-party/documents"),
                    })
                    self.assertFalse(inspected.isError)
                    self.assertEqual(inspected.structuredContent["capability"]["category"], "script")
                    document["components"][0]["type"] = "script"
                    rejected = await client.call_tool("skill2ui_evaluate", {"document": document, "state": {}})
                    self.assertTrue(rejected.isError)
                    report = {
                        "status": "passed",
                        "client": "Official Python MCP ClientSession",
                        "transport": "Actual spawned Skill2UI stdio process",
                        "protocol": initialized.protocolVersion,
                        "tools": sorted(by_name),
                        "resource": RESOURCE,
                        "resource_bytes": len(html.encode("utf-8")),
                        "calculation": {"total": 900, "people": 3, "tip": 20, "per_person": 360},
                        "checks": ["initialize", "tools/list", "resources/list", "resources/read", "tools/call", "Skill inspection", "invalid schema rejected"],
                        "limitations": ["No production Codex or Claude embedded host tested", "No Skill process execution exposed by this MCP adapter"],
                    }
                    output = PROJECT / "tests/artifacts/mcp-stdio-report.json"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
