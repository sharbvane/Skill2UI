import json
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from skill2ui.inspector import Inspector


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "demo"
        self.source.mkdir()
        (self.source / "SKILL.md").write_text("---\nname: demo\ndescription: Inspect CSV data.\nmetadata:\n  version: '1.2'\n---\n# Guide\n\nFollow these steps.", encoding="utf-8")
        self.inspector = Inspector(self.base / "data")

    def script(self, source, name="run.py"):
        scripts = self.source / "scripts"
        scripts.mkdir(exist_ok=True)
        (scripts / name).write_text(source, encoding="utf-8")

    def test_guide_yaml_inventory_digest_and_restart(self):
        (self.source / "references").mkdir()
        (self.source / "references" / "help.md").write_text("Details", encoding="utf-8")
        capability = self.inspector.import_path(self.source)
        self.assertEqual(capability["category"], "guide")
        self.assertEqual(capability["source"]["version"], "1.2")
        self.assertEqual(capability["resources"], ["references/help.md"])
        self.assertEqual(capability["actions"][0]["status"], "guide")
        self.assertEqual(Inspector(self.base / "data").get(capability["id"]), capability)
        capability["actions"].clear()
        self.assertEqual(len(self.inspector.get(capability["id"])["actions"]), 1)

    def test_import_snapshot_and_changed_source(self):
        capability = self.inspector.import_path(self.source)
        (self.source / "SKILL.md").write_text((self.source / "SKILL.md").read_text(encoding="utf-8") + "\nChanged", encoding="utf-8")
        self.inspector.verify(capability["id"])
        second = self.inspector.import_path(self.source)
        self.assertNotEqual(capability["id"], second["id"])
        (self.inspector.source_root(capability["id"]) / "SKILL.md").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.inspector.verify(capability["id"])
        (self.source / "SKILL.md").write_text("---\nname: demo\ndescription: Inspect CSV data.\nmetadata:\n  version: '1.2'\n---\n# Guide\n\nFollow these steps.", encoding="utf-8")
        restored = self.inspector.import_path(self.source)
        self.assertEqual(restored["id"], capability["id"])
        self.inspector.verify(restored["id"])

    def test_malformed_frontmatter(self):
        for content in ("# missing", "---\nname: demo", "---\nname: [oops]\ndescription: yes\n---", "---\nname: UpperCase\ndescription: test\n---", "---\nname: demo\ndescription: [\n---", "---\nname: demo\ndescription: !!python/object/apply:os.system ['echo unsafe']\n---"):
            with self.subTest(content=content):
                (self.source / "SKILL.md").write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.inspector.import_path(self.source)

    def test_argparse_recognition_never_runs_code(self):
        sentinel = self.base / "executed"
        self.script(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('BAD')\nimport argparse\np = argparse.ArgumentParser()\np.add_argument('files', nargs='+')\np.add_argument('--json', action='store_true')\np.add_argument('--count', type=int, default=2)\np.add_argument('--mode', choices=['quick', 'full'])\np.parse_args()")
        capability = self.inspector.import_path(self.source)
        action = capability["actions"][0]
        self.assertFalse(sentinel.exists())
        self.assertEqual(action["status"], "ready")
        self.assertEqual([(item["name"], item["type"]) for item in action["parameters"]], [("files", "file"), ("json", "boolean"), ("count", "integer"), ("mode", "choice")])

    def test_uncertain_argv_and_dynamic_argparse(self):
        self.script("import sys\nx = sys.argv[1]\nprint(x)")
        action = self.inspector.import_path(self.source)["actions"][0]
        self.assertEqual(action["status"], "needs_configuration")
        self.assertEqual(action["parameters"][0]["name"], "argument_1")
        self.script("import argparse\np=argparse.ArgumentParser()\nkwargs={'required': True}\np.add_argument('--input', **kwargs)\np.parse_args()")
        self.assertEqual(self.inspector.import_path(self.source)["actions"][0]["status"], "needs_configuration")

    def test_third_party_documents_parser(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "third-party" / "documents"
        if not source.exists():
            self.skipTest("Third-party fixture is not available")
        capability = self.inspector.import_path(source)
        self.assertEqual(capability["domain"], "pdf")
        action = next(item for item in capability["actions"] if item["id"] == "validate-documents")
        self.assertEqual(action["status"], "ready", action)
        self.assertEqual([item["name"] for item in action["parameters"]], ["files", "json", "render_check"])

    def test_missing_dependency(self):
        self.script("import skill2ui_definitely_missing_module\nimport argparse\np=argparse.ArgumentParser()\np.parse_args()")
        self.assertEqual(self.inspector.import_path(self.source)["actions"][0]["status"], "missing_dependency")

    def test_non_python_script_requires_configuration(self):
        self.script("console.log('hello')", name="run.js")
        capability = self.inspector.import_path(self.source)
        self.assertEqual(capability["category"], "script")
        self.assertEqual(capability["actions"][0]["status"], "needs_configuration")

    def test_reimport_refreshes_runtime_dependencies(self):
        self.script("import missing_module_for_refresh\nimport argparse\np=argparse.ArgumentParser()\np.parse_args()")
        first = self.inspector.import_path(self.source)
        self.assertEqual(first["actions"][0]["status"], "missing_dependency")
        with patch("skill2ui.inspector._missing", return_value=False):
            second = self.inspector.import_path(self.source)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["actions"][0]["status"], "ready")

    def test_manifest_rejects_mismatched_defaults_and_duplicate_flags(self):
        self.script("print('demo')")
        invalid = ([{"name": "count", "type": "integer", "default": "two"}],
                   [{"name": "verbose", "type": "boolean", "default": "yes"}],
                   [{"name": "mode", "type": "choice", "choices": ["a"], "default": "b"}],
                   [{"name": "one", "type": "string", "flag": "--same"}, {"name": "two", "type": "string", "flag": "--same"}])
        for parameters in invalid:
            with self.subTest(parameters=parameters):
                (self.source / "skill2ui.json").write_text(json.dumps({"actions": [{"id": "run", "script": "scripts/run.py", "parameters": parameters}]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.inspector.import_path(self.source)

    def test_explicit_tool_manifest_and_validation(self):
        manifest = {"version": 1, "category": "tool", "actions": [{"id": "inspect", "executable": "python", "args": ["--version"], "parameters": []}]}
        path = self.source / "skill2ui.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        capability = self.inspector.import_path(self.source)
        self.assertEqual(capability["category"], "tool")
        self.assertEqual(capability["actions"][0]["status"], "ready")
        for change in ({"script": "../escape.py", "executable": None}, {"executable": "powershell"}, {"parameters": [{"name": "bad", "type": "choice"}]}):
            with self.subTest(change=change):
                manifest["actions"][0] = {"id": "inspect", "executable": "python", **change}
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.inspector.import_path(self.source)

    def test_native_tool_manifest_infers_category_and_tool_guide(self):
        (self.source / "skill2ui.json").write_text(json.dumps({"actions": [{"id": "version", "executable": "git", "args": ["--version"]}]}), encoding="utf-8")
        capability = self.inspector.import_path(self.source)
        self.assertEqual(capability["category"], "tool")
        (self.source / "skill2ui.json").unlink()
        (self.source / "SKILL.md").write_text("---\nname: demo\ndescription: Search the web.\n---\nInvoke these MCP tools using the installed CLI.", encoding="utf-8")
        capability = self.inspector.import_path(self.source)
        self.assertEqual(capability["category"], "tool")
        self.assertEqual(capability["actions"][0]["status"], "needs_configuration")

    def test_zip_import_and_archive_attacks(self):
        path = self.base / "skill.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.write(self.source / "SKILL.md", "repo/demo/SKILL.md")
        capability = self.inspector.import_archive(path)
        self.assertEqual(capability["source"]["kind"], "archive")
        for name in ("../outside", "/absolute", "C:/escape", "nested/../../escape", "folder\\..\\escape", "NUL.txt", "name. "):
            with self.subTest(name=name):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(name, "bad")
                with self.assertRaises(ValueError):
                    self.inspector.import_archive(path)
        with zipfile.ZipFile(path, "w") as archive:
            link = zipfile.ZipInfo("symlink")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "/outside")
        with self.assertRaises(ValueError):
            self.inspector.import_archive(path)
        path.write_text("not a zip", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ZIP"):
            self.inspector.import_archive(path)
        self.assertFalse((self.base / "outside").exists())

    def test_archive_size_limits_and_duplicate_paths(self):
        path = self.base / "limit.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("big", "a" * 100)
        with patch("skill2ui.inspector.MAX_BYTES", 50):
            with self.assertRaises(ValueError):
                self.inspector.import_archive(path)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a", "1")
            archive.writestr("A", "2")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.inspector.import_archive(path)

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_windows_junction_rejected_without_copying_target(self):
        import subprocess
        target = self.base / "outside"
        target.mkdir()
        (target / "secret.txt").write_text("private", encoding="utf-8")
        junction = self.source / "references"
        # mklink is needed to construct the unsafe fixture; execution never invokes cmd.
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True)
        if result.returncode:
            self.skipTest("This environment cannot create a junction fixture")
        try:
            with self.assertRaisesRegex(ValueError, "junction"):
                self.inspector.import_path(self.source)
        finally:
            os.rmdir(junction)
        self.assertEqual((target / "secret.txt").read_text(encoding="utf-8"), "private")

    def test_github_rejects_unofficial_and_ambiguous_urls(self):
        for url in ("http://github.com/a/b", "https://evil.test/a/b", "https://github.com@evil.test/a/b", "https://github.com/a/b?token=private", "https://github.com/a/b/blob/main/SKILL.md", "https://github.com/a/../b", "https://github.com/a/b/tree/main/../../outside"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    self.inspector.import_github(url)

    def test_github_official_archive_selects_skill_subdirectory(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.write(self.source / "SKILL.md", "repo-deadbeef/skills/demo/SKILL.md")
            archive.writestr("repo-deadbeef/skills/other/SKILL.md", "---\nname: other\ndescription: Other skill.\n---")
            for index in range(2001):
                archive.writestr(f"repo-deadbeef/unrelated/{index}", "unrelated")
        payload.seek(0)
        with patch("skill2ui.inspector.urllib.request.build_opener") as factory:
            factory.return_value.open.return_value = payload
            capability = self.inspector.import_github("https://github.com/owner/repo/tree/deadbeef/skills/demo")
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://codeload.github.com/owner/repo/zip/deadbeef")
        self.assertEqual(capability["name"], "demo")
        self.assertEqual(capability["source"]["kind"], "github")


if __name__ == "__main__":
    unittest.main()
