"""Static Agent Skill inspection. Importing a skill never executes its code."""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
import zipfile

import yaml


MAX_FILES = 2000
MAX_BYTES = 100 * 1024 * 1024
MAX_TEXT = 1024 * 1024
IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".skill2ui"}
PARAM_TYPES = {"string", "number", "integer", "boolean", "file", "directory", "choice"}
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
FLAG = re.compile(r"^-{1,2}[A-Za-z][A-Za-z0-9_-]*$")


def _json_write(path: Path, value: object) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _is_link(path: Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def _files(root: Path) -> list[Path]:
    if _is_link(root):
        raise ValueError("Skill source root cannot be a link or junction")
    files, size = [], 0
    for base, directories, names in os.walk(root, followlinks=False):
        directories[:] = [name for name in directories if name not in IGNORED]
        for name in directories + names:
            path = Path(base) / name
            if _is_link(path):
                raise ValueError("Skill sources cannot contain symbolic links or junctions")
        for name in sorted(names):
            path = Path(base) / name
            if not path.is_file():
                raise ValueError("Only regular files are supported in a Skill")
            size += path.stat().st_size
            files.append(path)
            if len(files) > MAX_FILES or size > MAX_BYTES:
                raise ValueError("Skill exceeds the 2,000-file / 100 MiB import limit")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _files(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _text(path: Path) -> str:
    if path.stat().st_size > MAX_TEXT:
        raise ValueError(f"Text file exceeds 1 MiB: {path.name}")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Expected UTF-8 text: {path.name}") from exc


def _frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("SKILL.md frontmatter is not closed")
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise ValueError("Invalid SKILL.md YAML frontmatter") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Skill frontmatter must be an object")
    name, description = metadata.get("name"), metadata.get("description")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ValueError("Skill name must be a lowercase Agent Skills name of at most 64 characters")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError("Skill description must contain 1–1,024 characters")
    return metadata, "\n".join(lines[end + 1:]).strip()


def _literal(node: ast.AST):
    return ast.literal_eval(node)


def _input_type(name: str, declared: str = "str") -> str:
    if declared in {"int", "float"}:
        return {"int": "integer", "float": "number"}[declared]
    lower = name.lower()
    if any(word in lower for word in ("output", "dest", "save")):
        return "string"
    if any(word in lower for word in ("directory", "folder", "input_dir")):
        return "directory"
    if any(word in lower for word in ("input", "file", "csv", "pdf", "video", "image", "source")):
        return "file"
    return "string"


def _missing(dependency: str, root: Path) -> bool:
    kind, _, name = dependency.partition(":")
    if kind == "command":
        return shutil.which(name) is None
    if kind == "package":
        try:
            importlib.metadata.distribution(name)
            return False
        except importlib.metadata.PackageNotFoundError:
            return True
    module = name if kind == "module" else dependency
    module = module.split(".")[0]
    if module in sys.stdlib_module_names or (root / f"{module}.py").exists() or (root / module).is_dir() or (root / "scripts" / f"{module}.py").exists():
        return False
    try:
        return importlib.util.find_spec(module) is None
    except (ValueError, ModuleNotFoundError):
        return True


def _python_action(path: Path, root: Path) -> tuple[dict, dict]:
    relative = path.relative_to(root).as_posix()
    action = {"id": re.sub(r"[^A-Za-z0-9_-]", "-", path.stem), "label": path.stem.replace("_", " ").title(),
              "description": f"Run {relative}", "status": "needs_configuration", "script": relative,
              "interpreter": sys.executable, "parameters": [], "permissions": ["execute_local_code"], "dependencies": []}
    config = {"bindings": {}, "timeout": 120, "fixed_args": []}
    try:
        tree = ast.parse(_text(path), filename=relative)
    except (SyntaxError, ValueError):
        action["description"] += " (static parsing failed)"
        return action, config
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            action["dependencies"].extend(f"module:{entry.name.split('.')[0]}" for entry in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            action["dependencies"].append(f"module:{node.module.split('.')[0]}")
    action["dependencies"] = sorted(set(action["dependencies"]))
    parsers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            function = node.value.func
            if (isinstance(function, ast.Attribute) and function.attr == "ArgumentParser") or (isinstance(function, ast.Name) and function.id == "ArgumentParser"):
                parsers.update(target.id for target in node.targets if isinstance(target, ast.Name))
    uncertain = False
    has_parse = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name) or node.func.value.id not in parsers:
            continue
        if node.func.attr in {"parse_args", "parse_known_args"}:
            has_parse = True
            if node.func.attr == "parse_known_args":
                uncertain = True
            if node.args and not (len(node.args) == 1 and isinstance(node.args[0], ast.Name)):
                uncertain = True
        if node.func.attr in {"add_subparsers", "add_mutually_exclusive_group"}:
            uncertain = True
        if node.func.attr != "add_argument":
            continue
        if any(keyword.arg == "action" and isinstance(keyword.value, ast.Constant) and keyword.value.value in {"help", "version"} for keyword in node.keywords):
            continue
        try:
            flags = [_literal(arg) for arg in node.args]
            if not flags or any(not isinstance(flag, str) for flag in flags):
                raise ValueError("Dynamic argument")
            kwargs = {keyword.arg: (_literal(keyword.value) if keyword.arg != "type" else getattr(keyword.value, "id", "unknown")) for keyword in node.keywords}
            if None in kwargs:
                raise ValueError("Expanded keyword arguments")
            flag = max(flags, key=len)
            positional = not flag.startswith("-")
            name = kwargs.get("dest", flag.lstrip("-").replace("-", "_"))
            behavior = kwargs.get("action", "store")
            if behavior not in {"store", "store_true", "store_false"} or kwargs.get("nargs") not in {None, "?", "+"} or kwargs.get("type", "str") not in {"str", "int", "float", "Path"}:
                uncertain = True
            parameter = {"name": name, "label": name.replace("_", " ").title(), "type": _input_type(name, kwargs.get("type", "str")),
                         "required": kwargs.get("required", positional and kwargs.get("nargs") != "?"), "positional": positional}
            if not positional:
                parameter["flag"] = flag
            if behavior in {"store_true", "store_false"}:
                parameter["type"] = "boolean"
                parameter["default"] = kwargs.get("default", behavior == "store_false")
            elif "default" in kwargs and kwargs["default"] is not None:
                parameter["default"] = kwargs["default"]
            if "choices" in kwargs:
                parameter["type"] = "choice"
                parameter["choices"] = [str(value) for value in kwargs["choices"]]
                if "default" in parameter:
                    parameter["default"] = str(parameter["default"])
            if "help" in kwargs and isinstance(kwargs["help"], str):
                parameter["label"] = kwargs["help"]
            action["parameters"].append(parameter)
            config["bindings"][name] = behavior
        except (ValueError, TypeError):
            uncertain = True
    # shortcut: nargs='+' accepts one selected value in this GUI; add array parameters when multi-file UI is needed.
    # shortcut: only literal argparse declarations are executable automatically; use skill2ui.json for dynamic parsers.
    if parsers and has_parse and not uncertain:
        action["status"] = "ready"
    elif not action["parameters"]:
        indices = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == "sys" and node.value.attr == "argv":
                try:
                    index = _literal(node.slice)
                    if isinstance(index, int) and index > 0:
                        indices[index] = {"name": f"argument_{index}", "label": f"Argument {index} (verify configuration)", "type": "string", "required": True, "positional": True}
                except (ValueError, TypeError):
                    pass
        action["parameters"] = [indices[index] for index in sorted(indices)]
    if any(_missing(dep, root) for dep in action["dependencies"]):
        action["status"] = "missing_dependency"
    return action, config


def _validate_action(raw: dict, root: Path) -> tuple[dict, dict]:
    if not isinstance(raw, dict) or not NAME.fullmatch(str(raw.get("id", ""))):
        raise ValueError("Manifest actions require a valid id")
    script, executable = raw.get("script"), raw.get("executable")
    if bool(script) == bool(executable):
        raise ValueError("Each manifest action needs either script or executable")
    action = {"id": raw["id"], "label": str(raw.get("label", raw["id"])), "description": str(raw.get("description", "Explicitly configured local action")),
              "status": "ready", "parameters": [], "permissions": ["execute_local_code"], "dependencies": raw.get("dependencies", [])}
    interpreter = raw.get("interpreter", "python")
    if script:
        if not isinstance(script, str) or Path(script).is_absolute() or ".." in PurePosixPath(script.replace("\\", "/")).parts:
            raise ValueError("Manifest script must be relative to its Skill")
        target = (root / script).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            raise ValueError("Manifest script is missing or outside the Skill")
        action["script"] = target.relative_to(root.resolve()).as_posix()
        if interpreter in {"python", "python3", "python3.11"}:
            interpreter = sys.executable
        elif interpreter not in {"node", "ruby", "perl"}:
            raise ValueError("Supported script interpreters: python, node, ruby, perl")
        action["interpreter"] = interpreter
        if shutil.which(interpreter) is None:
            action["status"] = "missing_dependency"
    else:
        if not isinstance(executable, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", executable) or executable.lower() in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe", "sh", "bash", "zsh"}:
            raise ValueError("Tool executable must be a registered command name, not a shell or path")
        action["interpreter"] = executable
        if shutil.which(executable) is None:
            action["status"] = "missing_dependency"
    if not isinstance(action["dependencies"], list) or any(not isinstance(dep, str) for dep in action["dependencies"]):
        raise ValueError("Action dependencies must be strings")
    if any(_missing(dep, root) for dep in action["dependencies"]):
        action["status"] = "missing_dependency"
    permissions = raw.get("permissions", [])
    if not isinstance(permissions, list) or any(not isinstance(value, str) or len(value) > 100 for value in permissions):
        raise ValueError("Action permissions must be strings")
    action["permissions"] = sorted(set(action["permissions"] + permissions))
    parameters = raw.get("parameters", [])
    if not isinstance(parameters, list) or len(parameters) > 100:
        raise ValueError("Action parameters must be a list of at most 100 parameters")
    names, flags, bindings = set(), set(), {}
    optional_positional = False
    for parameter in parameters:
        if not isinstance(parameter, dict) or not NAME.fullmatch(str(parameter.get("name", ""))) or parameter["name"] in names or parameter.get("type") not in PARAM_TYPES:
            raise ValueError("Invalid or duplicate action parameter")
        if not isinstance(parameter.get("required", False), bool) or not isinstance(parameter.get("positional", False), bool):
            raise ValueError("Parameter required/positional must be booleans")
        name, kind = parameter["name"], parameter["type"]
        names.add(name)
        item = {"name": name, "label": str(parameter.get("label", name)), "type": kind,
                "required": parameter.get("required", False), "positional": parameter.get("positional", False)}
        if item["positional"]:
            if kind == "boolean" or optional_positional:
                raise ValueError("Boolean or ambiguous optional positional arguments are unsupported")
            optional_positional = not item["required"]
        else:
            flag = parameter.get("flag", "--" + name.replace("_", "-"))
            if not isinstance(flag, str) or not FLAG.fullmatch(flag):
                raise ValueError("Invalid parameter flag")
            if flag in flags:
                raise ValueError("Duplicate parameter flags")
            flags.add(flag)
            item["flag"] = flag
        if "default" in parameter:
            item["default"] = parameter["default"]
            default = parameter["default"]
            if default is not None and ((kind == "boolean" and not isinstance(default, bool)) or
                                        (kind == "integer" and type(default) is not int) or
                                        (kind == "number" and (type(default) not in {int, float} or not (-1e308 <= default <= 1e308))) or
                                        (kind in {"string", "file", "directory", "choice"} and not isinstance(default, str))):
                raise ValueError("Parameter default does not match its type")
        if kind == "choice":
            choices = parameter.get("choices")
            if not isinstance(choices, list) or not choices or any(not isinstance(choice, str) for choice in choices):
                raise ValueError("Choice parameters require nonempty string choices")
            item["choices"] = choices
            if "default" in item and item["default"] is not None and item["default"] not in choices:
                raise ValueError("Choice default is not an allowed choice")
        behavior = parameter.get("action", "store_true" if kind == "boolean" else "store")
        if behavior not in {"store", "store_true", "store_false"} or (kind == "boolean") != (behavior != "store"):
            raise ValueError("Boolean parameters require store_true or store_false")
        bindings[name] = behavior
        action["parameters"].append(item)
    fixed_args = raw.get("args", [])
    timeout = raw.get("timeout", 120)
    if not isinstance(fixed_args, list) or any(not isinstance(arg, str) or "\0" in arg for arg in fixed_args) or len(fixed_args) > 100:
        raise ValueError("Fixed action args must be strings")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 3600:
        raise ValueError("Action timeout must be between 1 and 3,600 seconds")
    return action, {"bindings": bindings, "fixed_args": fixed_args, "timeout": timeout}


class Inspector:
    def __init__(self, data_dir: Path):
        self.directory = Path(data_dir).resolve() / "skills"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records = {}
        for path in sorted(self.directory.glob("*/capability.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["capability"]["id"] == path.parent.name:
                    self._records[path.parent.name] = record
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def list(self) -> list[dict]:
        with self._lock:
            return [self.get(identifier) for identifier in self._records]

    def get(self, identifier: str) -> dict:
        with self._lock:
            if identifier not in self._records:
                raise FileNotFoundError("Skill not found")
            return copy.deepcopy(self._records[identifier]["capability"])

    def source_root(self, identifier: str) -> Path:
        self.get(identifier)
        return self.directory / identifier / "source"

    def verify(self, identifier: str) -> str:
        expected = self.get(identifier)["source"]["sha256"]
        if source_digest(self.source_root(identifier)) != expected:
            raise ValueError("Imported Skill source changed; re-import and approve it again")
        return expected

    def action_config(self, identifier: str, action_id: str) -> dict:
        self.get(identifier)
        try:
            return copy.deepcopy(self._records[identifier]["config"][action_id])
        except KeyError as exc:
            raise ValueError("Action not found") from exc

    def import_path(self, path: str | Path) -> dict:
        source = Path(path).expanduser().resolve()
        if source.is_file() and source.name.upper() == "SKILL.MD":
            source = source.parent
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            raise FileNotFoundError("Select a Skill directory containing SKILL.md")
        return self._import(source, {"kind": "local", "path": str(source)})

    def _import(self, source: Path, origin: dict) -> dict:
        with self._lock:
            return self._import_locked(source, origin)

    def _import_locked(self, source: Path, origin: dict) -> dict:
        metadata, instructions = _frontmatter(_text(source / "SKILL.md"))
        source_files = _files(source)
        digest = source_digest(source)
        identifier = metadata["name"] + "-" + digest[:12]
        restore_snapshot = False
        if identifier in self._records:
            try:
                self.verify(identifier)
            except ValueError:
                restore_snapshot = True
        manifest = {}
        if (source / "skill2ui.json").exists():
            try:
                manifest = json.loads(_text(source / "skill2ui.json"))
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid skill2ui.json") from exc
            if not isinstance(manifest, dict) or manifest.get("version", 1) != 1:
                raise ValueError("skill2ui.json requires schema version 1")
        actions, config, warnings = [], {}, []
        if "actions" in manifest:
            if not isinstance(manifest["actions"], list) or len(manifest["actions"]) > 30:
                raise ValueError("Manifest actions must be a list of at most 30 actions")
            for raw in manifest["actions"]:
                action, settings = _validate_action(raw, source)
                actions.append(action)
                config[action["id"]] = settings
        else:
            scripts = [path for path in source_files if path.suffix.lower() == ".py" and "scripts" in path.relative_to(source).parts]
            for path in scripts:
                action, settings = _python_action(path, source)
                actions.append(action)
                config[action["id"]] = settings
            other_scripts = [path for path in source_files if path.suffix.lower() in {".sh", ".ps1", ".js", ".ts", ".rb"} and "scripts" in path.relative_to(source).parts]
            if other_scripts:
                warnings.append("Non-Python scripts require an explicit skill2ui.json execution binding; shell scripts are not executed.")
                for path in other_scripts:
                    actions.append({"id": re.sub(r"[^A-Za-z0-9_-]", "-", path.stem), "label": path.stem.replace("_", " ").title(),
                                    "description": "Configure the actual interpreter and parameters before execution", "status": "needs_configuration",
                                    "script": path.relative_to(source).as_posix(), "parameters": [], "permissions": ["execute_local_code"], "dependencies": []})
        ids = [action["id"] for action in actions]
        if len(actions) > 30:
            raise ValueError("At most 30 actions per Skill are supported; select its runnable actions in skill2ui.json")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate action ids; configure unique ids in skill2ui.json")
        category = manifest.get("category", "script" if any("script" in action for action in actions) else "tool" if actions else "guide")
        if category not in {"script", "tool", "guide"}:
            raise ValueError("Invalid Skill category")
        if category == "guide" and actions:
            raise ValueError("Guide Skills cannot declare executable actions")
        if not actions:
            if re.search(r"\b(mcp|tool|cli|command)\b", metadata["description"] + " " + instructions, re.I) and category != "guide":
                category = "tool"
            elif "category" not in manifest and re.search(r"\b(mcp|tool|cli)\b", instructions, re.I):
                category = "tool"
            actions = [{"id": "guide", "label": "Follow Skill instructions", "description": "Read the original instructions and complete steps with your Agent.", "status": "needs_configuration" if category == "tool" else "guide", "parameters": [], "permissions": [], "dependencies": []}]
            warnings.append("No executable interface is verified; instructions are available as an interactive guide.")
        if any(action["status"] == "needs_configuration" for action in actions):
            warnings.append("Some arguments are uncertain. Add skill2ui.json before enabling execution.")
        if any(action["status"] == "missing_dependency" for action in actions):
            warnings.append("Required runtime dependencies are missing. Install them in the server environment and re-import the Skill.")
        combined = (metadata["name"] + " " + metadata["description"]).lower()
        scores = {domain: sum(combined.count(word) + 3 * metadata["name"].count(word) for word in keywords) for domain, keywords in {"video": ("video", "视频", "montage"), "pdf": ("pdf", "document", "文档"), "data": ("data", "csv", "数据", "分析"), "automation": ("automation", "自动化", "browser")}.items()}
        domain = max(scores, key=scores.get) if max(scores.values()) else "general"
        version = metadata.get("metadata", {}).get("version", digest[:12]) if isinstance(metadata.get("metadata", {}), dict) else digest[:12]
        capability = {"id": identifier, "name": metadata["name"], "description": metadata["description"], "category": category, "domain": domain,
                      "source": {**origin, "version": str(version), "sha256": digest}, "instructions": instructions,
                      "resources": [path.relative_to(source).as_posix() for path in source_files if path.name != "SKILL.md"], "actions": actions, "warnings": warnings}
        destination = self.directory / identifier
        record = {"capability": capability, "config": config}
        if identifier in self._records and not restore_snapshot:
            _json_write(destination / "capability.json", record)
            self._records[identifier] = record
            return self.get(identifier)
        with tempfile.TemporaryDirectory(prefix="import-", dir=self.directory) as temporary:
            staging = Path(temporary)
            (staging / "source").mkdir()
            for path in source_files:
                target = staging / "source" / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            if source_digest(staging / "source") != digest:
                raise ValueError("Skill source changed during import; retry")
            _json_write(staging / "capability.json", record)
            if restore_snapshot:
                # Keep modified sources for inspection; restore only on an explicit re-import.
                current = destination / "source"
                if current.exists() or _is_link(current):
                    current.replace(destination / ("source-before-reimport-" + staging.name))
                (staging / "source").replace(current)
                _json_write(destination / "capability.json", record)
            else:
                shutil.copytree(staging, destination)
        self._records[identifier] = record
        return self.get(identifier)

    def import_archive(self, path: str | Path, *, origin: dict | None = None, subpath: str | None = None) -> dict:
        archive_path = Path(path)
        if not archive_path.is_file():
            raise FileNotFoundError("Archive not found")
        if archive_path.stat().st_size > MAX_BYTES:
            raise ValueError("Archive exceeds the 100 MiB limit")
        if subpath and (Path(subpath).is_absolute() or any(part in {".", ".."} or ":" in part for part in PurePosixPath(subpath.replace("\\", "/")).parts)):
            raise ValueError("Archive Skill subpath must stay inside its repository")
        with tempfile.TemporaryDirectory(prefix="archive-", dir=self.directory) as temporary:
            root = Path(temporary)
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    members = archive.infolist()
                    if len(members) > 50000:
                        raise ValueError("Archive exceeds the 50,000-entry metadata limit")
                    if subpath:
                        prefix = subpath.replace("\\", "/").strip("/")
                        members = [item for item in members if (item.filename.replace("\\", "/").partition("/")[2].rstrip("/") == prefix or item.filename.replace("\\", "/").partition("/")[2].startswith(prefix + "/"))]
                    if len(members) > MAX_FILES or sum(item.file_size for item in members) > MAX_BYTES:
                        raise ValueError("Expanded archive exceeds import limits")
                    seen = set()
                    for member in members:
                        normalized = member.filename.replace("\\", "/")
                        parts = PurePosixPath(normalized).parts
                        mode = member.external_attr >> 16
                        if not parts or normalized.startswith("/") or any(part in {"..", "."} or ":" in part or "\0" in part for part in parts) or stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                            raise ValueError("Unsafe archive path or special file")
                        if any(part.rstrip(" .") != part or part.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))} for part in parts):
                            raise ValueError("Unsafe Windows archive filename")
                        key = normalized.rstrip("/").casefold()
                        if key in seen:
                            raise ValueError("Duplicate archive paths")
                        seen.add(key)
                        target = root.joinpath(*parts)
                        if not target.resolve().is_relative_to(root.resolve()):
                            raise ValueError("Archive path escapes its root")
                        if member.is_dir():
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            with archive.open(member) as incoming, target.open("wb") as output:
                                shutil.copyfileobj(incoming, output)
            except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
                raise ValueError("Cannot read ZIP archive") from exc
            candidates = sorted(root.rglob("SKILL.md"))
            if subpath:
                prefixes = [path for path in root.iterdir() if path.is_dir()]
                candidates = [prefix / subpath / "SKILL.md" for prefix in prefixes if (prefix / subpath / "SKILL.md").is_file()]
            if len(candidates) != 1:
                raise ValueError("Archive must identify one Skill; GitHub repositories with multiple Skills need a /tree/ref/skill/path URL")
            return self._import(candidates[0].parent, origin or {"kind": "archive", "path": str(archive_path.resolve())})

    def import_github(self, url: str) -> dict:
        parsed = urllib.parse.urlparse(url)
        parts = parsed.path.strip("/").split("/")
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment or len(parts) < 2 or any(part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
            raise ValueError("Use an official https://github.com/owner/repository URL")
        owner, repository = parts[:2]
        repository = repository.removesuffix(".git")
        reference, subpath = None, None
        if len(parts) > 2:
            if len(parts) < 4 or parts[2] != "tree":
                raise ValueError("Use a repository or /tree/ref/skill/path GitHub URL")
            reference = parts[3]
            subpath = "/".join(parts[4:]) or None
        # shortcut: refs containing slashes need an archive import; GitHub tree URLs are ambiguous without its API.
        archive_url = f"https://codeload.github.com/{owner}/{repository}/zip/" + (urllib.parse.quote(reference, safe="") if reference else "HEAD")
        class OfficialRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, message, headers, newurl):
                target = urllib.parse.urlparse(newurl)
                if target.scheme != "https" or target.netloc.lower() not in {"github.com", "codeload.github.com"}:
                    raise ValueError("GitHub download redirected outside official HTTPS hosts")
                return super().redirect_request(request, fp, code, message, headers, newurl)
        with tempfile.TemporaryDirectory(prefix="github-", dir=self.directory) as temporary:
            path = Path(temporary) / "skill.zip"
            try:
                opener = urllib.request.build_opener(OfficialRedirect())
                with opener.open(urllib.request.Request(archive_url, headers={"User-Agent": "Skill2UI/0.1"}), timeout=30) as response, path.open("wb") as output:
                    count = 0
                    for chunk in iter(lambda: response.read(65536), b""):
                        count += len(chunk)
                        if count > MAX_BYTES:
                            raise ValueError("GitHub archive exceeds 100 MiB")
                        output.write(chunk)
            except OSError as exc:
                raise ValueError(f"GitHub archive download failed: {exc}") from exc
            return self.import_archive(path, origin={"kind": "github", "path": url}, subpath=subpath)
