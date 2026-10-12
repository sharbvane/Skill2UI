import asyncio
import tempfile
import unittest

from skill2ui.mcp_server import RESOURCE, build_server


class MCPTests(unittest.TestCase):
    def test_official_sdk_tools_resource_and_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            server = build_server(directory)
            async def check():
                tools = await server.list_tools()
                self.assertEqual({tool.name for tool in tools}, {"skill2ui_generate", "skill2ui_evaluate", "skill2ui_inspect"})
                generate = next(t for t in tools if t.name == "skill2ui_generate")
                self.assertEqual(generate.meta["ui"]["resourceUri"], RESOURCE)
                content, result = await server.call_tool("skill2ui_generate", {"prompt": "AA费用计算器"})
                doc = result["document"]
                content, result = await server.call_tool("skill2ui_evaluate", {"document": doc, "state": {"total": 120, "people": 2, "tip": 0}})
                self.assertEqual(result["metrics"]["per_person"], 60)
                resources = await server.list_resources()
                self.assertEqual(resources[0].mimeType, "text/html;profile=mcp-app")
                resource = await server.read_resource(RESOURCE)
                self.assertIn("<!doctype html>", resource[0].content)
                self.assertNotIn("http://127.0.0.1", resource[0].content)
            asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
