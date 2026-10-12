"""Portable entry points for agents and people."""
import argparse
import json
import shutil
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .generation import Generator, skill_document
from .schema import UIDocument


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(prog="skill2ui", description="Generate interfaces from requests and Agent Skills")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Run the loopback browser workbench")
    serve.add_argument("--port", type=int, default=7860)
    serve.add_argument("--data-dir", default=".skill2ui")
    serve.add_argument("--open", action="store_true")
    generate = sub.add_parser("generate", help="Write a validated UI document to stdout")
    generate.add_argument("prompt")
    generate.add_argument("--current", help="Existing UI JSON for an edit")
    inspect = sub.add_parser("inspect", help="Statically import a Skill without executing it")
    inspect.add_argument("path")
    inspect.add_argument("--data-dir", default=".skill2ui")
    inspect.add_argument("--gui", action="store_true")
    mcp = sub.add_parser("mcp", help="Run the stdio MCP adapter")
    mcp.add_argument("--data-dir", default=".skill2ui")
    install = sub.add_parser("install-skill", help="Install Skill instructions in an Agent's skills directory")
    install.add_argument("--host", choices=["codex", "claude"], required=True)
    install.add_argument("--directory", help="Override skills parent directory")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            if not 1 <= args.port <= 65535:
                parser.error("Port must be between 1 and 65535")
            import uvicorn
            from .api import create_app
            app = create_app(args.data_dir)
            print(f"Skill2UI {__version__} — http://127.0.0.1:{args.port}")
            if args.open:
                webbrowser.open(f"http://127.0.0.1:{args.port}")
            uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        elif args.command == "generate":
            existing = UIDocument.model_validate_json(Path(args.current).read_text(encoding="utf-8")) if args.current else None
            emit(Generator().generate(args.prompt, existing))
        elif args.command == "inspect":
            from .inspector import Inspector
            inspector = Inspector(Path(args.data_dir).resolve())
            capability = inspector.import_github(args.path) if args.path.startswith("https://github.com/") else inspector.import_path(args.path)
            emit(skill_document(capability).model_dump() if args.gui else capability)
        elif args.command == "mcp":
            from .mcp_server import run
            run(Path(args.data_dir).resolve())
        elif args.command == "install-skill":
            source = Path(__file__).parent / "agent" / "skill2ui"
            target = (Path(args.directory).expanduser() if args.directory else Path.home() / (".codex/skills" if args.host == "codex" else ".claude/skills")) / "skill2ui"
            if target.exists():
                raise ValueError(f"Destination already exists: {target}; remove or back it up explicitly before reinstalling")
            shutil.copytree(source, target)
            emit({"installed": str(target), "host": args.host})
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
