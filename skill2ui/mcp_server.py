"""Official MCP SDK adapter. Embedded UI never grants script execution."""
from pathlib import Path
from typing import Any

from . import __version__
from .generation import Generator, skill_document
from .inspector import Inspector
from .schema import UIDocument, evaluate

RESOURCE = "ui://skill2ui/app.html"


def build_server(data_dir):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ValueError("Install MCP support with: pip install 'skill2ui[mcp]'") from exc
    server = FastMCP("Skill2UI")
    # FastMCP has no application-version constructor argument.
    server._mcp_server.version = __version__
    generator, inspector = Generator(), Inspector(Path(data_dir))

    @server.tool(name="skill2ui_generate", meta={"ui": {"resourceUri": RESOURCE}}, structured_output=True)
    def generate_ui(prompt: str, document: dict | None = None, state: dict | None = None) -> dict[str, Any]:
        """Generate or edit an interactive interface. Supports a host-rendered MCP App."""
        existing = UIDocument.model_validate(document) if document else None
        return generator.generate(prompt, existing, state)

    @server.tool(name="skill2ui_evaluate", meta={"ui": {"visibility": ["app"]}}, structured_output=True)
    def evaluate_ui(document: dict, state: dict) -> dict[str, Any]:
        """Compute validated UI arithmetic. Does not execute Skills."""
        return {"metrics": evaluate(UIDocument.model_validate(document), state)}

    @server.tool(name="skill2ui_inspect", meta={"ui": {"resourceUri": RESOURCE}}, structured_output=True)
    def inspect_skill(path: str) -> dict[str, Any]:
        """Statically inspect a local Agent Skill and display its recognized inputs."""
        capability = inspector.import_path(path)
        return {"document": skill_document(capability).model_dump(), "capability": capability}

    @server.resource(RESOURCE, name="Skill2UI interactive tool", mime_type="text/html;profile=mcp-app", meta={"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}})
    def app_resource() -> str:
        bundle = Path(__file__).parent / "web" / "mcp" / "app.js"
        if not bundle.is_file():
            raise ValueError("MCP UI bundle missing; run npm ci and npm run build:mcp in the source checkout")
        code = bundle.read_text(encoding="utf-8").replace("</script", "<\\/script")
        return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="app"></main><script type="module">' + code + "</script></body></html>"

    return server


def run(data_dir):
    build_server(data_dir).run(transport="stdio")
