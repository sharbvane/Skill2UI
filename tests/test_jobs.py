import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from skill2ui.inspector import Inspector
from skill2ui.jobs import JobManager


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / "demo"
        (self.source / "scripts").mkdir(parents=True)
        (self.source / "SKILL.md").write_text("---\nname: demo\ndescription: Runtime test.\n---\nRun demo.", encoding="utf-8")
        self.inspector = Inspector(self.base / "data")
        self.jobs = JobManager(self.inspector, self.base / "data")

    def action(self, code, parameters=None, timeout=10):
        (self.source / "scripts" / "run.py").write_text(code, encoding="utf-8")
        (self.source / "skill2ui.json").write_text(json.dumps({"version": 1, "actions": [{"id": "run", "script": "scripts/run.py", "timeout": timeout, "parameters": parameters or []}]}), encoding="utf-8")
        return self.inspector.import_path(self.source)["id"]

    def run_action(self, skill, arguments=None):
        approval = self.jobs.prepare(skill, "run", arguments or {})
        job = self.jobs.start(approval["approval_id"], True)
        return self.wait(job["id"])

    def wait(self, identifier, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.jobs.get(identifier)
            if job["status"] not in {"queued", "running"}:
                return job
            time.sleep(0.05)
        self.jobs.cancel(identifier)
        self.fail("Job did not terminate within test deadline")

    def test_csv_end_to_end_result_and_real_artifacts(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "csv-summary"
        capability = self.inspector.import_path(source)
        approval = self.jobs.prepare(capability["id"], "summarize", {"input": str(source / "assets" / "example.csv"), "precision": 2})
        self.assertIn("not an OS sandbox", approval["warning"])
        self.assertEqual(approval["command"][-1], "--precision=2")
        job = self.wait(self.jobs.start(approval["approval_id"], True)["id"])
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"]["rows"], 3)
        self.assertEqual(job["result"]["columns"][1]["sum"], 132)
        self.assertEqual({item["name"] for item in job["artifacts"]}, {"result.json", "summary.csv"})
        self.assertEqual(json.loads(self.jobs.artifact(job["id"], "result.json").read_text(encoding="utf-8"))["rows"], 3)
        with self.assertRaises(FileNotFoundError):
            self.jobs.artifact(job["id"], "../../job.json")
        self.assertEqual(JobManager(self.inspector, self.base / "data").get(job["id"])["status"], "succeeded")

    def test_input_types_unknown_fields_and_required_validation(self):
        parameters = [{"name": "count", "type": "integer", "required": True}, {"name": "ratio", "type": "number"}, {"name": "mode", "type": "choice", "choices": ["a", "b"]}, {"name": "input", "type": "file"}, {"name": "folder", "type": "directory"}, {"name": "verbose", "type": "boolean"}]
        skill = self.action("print('hello')", parameters)
        for arguments in ({}, {"count": True}, {"count": 2.5}, {"count": "2"}, {"count": 2, "ratio": float("nan")}, {"count": 2, "mode": "x"}, {"count": 2, "input": "missing"}, {"count": 2, "folder": str(self.source / "SKILL.md")}, {"count": 2, "verbose": "yes"}, {"count": 2, "unknown": "x"}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.jobs.prepare(skill, "run", arguments)

    def test_approval_single_use_exact_command_and_confirmation(self):
        skill = self.action("print('done')", [{"name": "text", "type": "string"}])
        approval = self.jobs.prepare(skill, "run", {"text": "hello; echo BAD $(whoami)"})
        self.assertEqual(approval["command"][-1], "--text=hello; echo BAD $(whoami)")
        with self.assertRaisesRegex(ValueError, "confirmation"):
            self.jobs.start(approval["approval_id"], False)
        job = self.wait(self.jobs.start(approval["approval_id"], True)["id"])
        self.assertEqual(job["status"], "succeeded")
        with self.assertRaisesRegex(ValueError, "already used"):
            self.jobs.start(approval["approval_id"], True)
        with self.assertRaises(ValueError):
            self.jobs.start("invented", True)

    def test_tampering_invalidates_approval_and_expiration(self):
        skill = self.action("print('done')")
        approval = self.jobs.prepare(skill, "run", {})
        (self.inspector.source_root(skill) / "scripts" / "run.py").write_text("print('changed')", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.jobs.start(approval["approval_id"], True)
        with self.assertRaises(ValueError):
            self.jobs.prepare(skill, "run", {})
        skill = self.action("print('fresh')")
        approval = self.jobs.prepare(skill, "run", {})
        self.jobs._approvals[approval["approval_id"]]["prepared_at"] -= 901
        with self.assertRaisesRegex(ValueError, "expired"):
            self.jobs.start(approval["approval_id"], True)

    def test_credentials_removed_and_command_never_uses_shell(self):
        skill = self.action("import json, os\nfrom pathlib import Path\nPath('result.json').write_text(json.dumps({'secret': os.getenv('OPENAI_API_KEY'), 'token': os.getenv('GITHUB_TOKEN'), 'custom': os.getenv('PRIVATE_CONFIG'), 'home': os.getenv('HOME')}))")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET", "GITHUB_TOKEN": "TOKEN", "PRIVATE_CONFIG": "PRIVATE"}), patch("skill2ui.jobs.subprocess.Popen", wraps=subprocess.Popen) as popen:
            job = self.run_action(skill)
        self.assertEqual(job["status"], "succeeded", job)
        self.assertIsNone(job["result"]["secret"])
        self.assertIsNone(job["result"]["token"])
        self.assertIsNone(job["result"]["custom"])
        self.assertIn(job["id"], job["result"]["home"])
        self.assertFalse(popen.call_args.kwargs["shell"])

    def test_sensitive_argument_redacted_across_log_chunks_and_persistence(self):
        secret = "sk-sensitive-credential-123456789"
        skill = self.action("import argparse, sys, time\np=argparse.ArgumentParser()\np.add_argument('--api-key', required=True)\na=p.parse_args()\nsys.stdout.write('prefix ' + a.api_key[:8]); sys.stdout.flush(); time.sleep(.15)\nsys.stdout.write(a.api_key[8:] + ' suffix\\n'); sys.stdout.flush()", [{"name": "api_key", "type": "string", "required": True}])
        approval = self.jobs.prepare(skill, "run", {"api_key": secret})
        self.assertEqual(approval["command"][-1], "--api-key=" + secret)
        job = self.wait(self.jobs.start(approval["approval_id"], True)["id"])
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["command"][-1], "--api-key=[REDACTED]")
        self.assertEqual("".join(job["logs"]).replace("\r\n", "\n"), "prefix [REDACTED] suffix\n")
        persisted = (self.jobs.directory / job["id"] / "job.json").read_text(encoding="utf-8")
        self.assertNotIn(secret, persisted)
        self.assertNotIn(secret[:8], persisted)
        self.assertEqual(JobManager(self.inspector, self.base / "data").get(job["id"])["command"][-1], "--api-key=[REDACTED]")

    def test_json_escaped_credential_not_in_result_or_stdout_artifact(self):
        secret = 'secret-"中文"-with\\slash'
        skill = self.action("import argparse, json\np=argparse.ArgumentParser()\np.add_argument('--password')\na=p.parse_args()\nprint(json.dumps({'password': a.password}))", [{"name": "password", "type": "string"}])
        job = self.run_action(skill, {"password": secret})
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["result"], {"password": "[REDACTED]"})
        stdout = self.jobs.artifact(job["id"], "_skill2ui_stdout.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(stdout), {"password": "[REDACTED]"})

    def test_failed_process_and_timeout(self):
        skill = self.action("raise RuntimeError('real failure')")
        job = self.run_action(skill)
        self.assertEqual(job["status"], "failed")
        self.assertIn("RuntimeError: real failure", "".join(job["logs"]))
        skill = self.action("import time\ntime.sleep(5)", timeout=1)
        job = self.run_action(skill)
        self.assertEqual(job["status"], "failed")
        self.assertIn("timeout", job["error"])

    def test_cancellation_kills_child_tree(self):
        marker = self.base / "child-survived.txt"
        child_code = f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).write_text('BAD')"
        skill = self.action(f"import subprocess, sys, time\nfrom pathlib import Path\nchild = subprocess.Popen([sys.executable, '-c', {child_code!r}])\nPath('child-started').write_text(str(child.pid))\ntime.sleep(20)", timeout=25)
        approval = self.jobs.prepare(skill, "run", {})
        job = self.jobs.start(approval["approval_id"], True)
        started = self.jobs.directory / job["id"] / "work" / "child-started"
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(started.exists())
        self.jobs.cancel(job["id"])
        self.assertEqual(self.wait(job["id"])["status"], "cancelled")
        time.sleep(2.2)
        self.assertFalse(marker.exists(), "Cancelled child process survived")

    def test_log_cap_and_unicode_output(self):
        skill = self.action("print('测' * 4000)\nprint('x' * 300000)")
        job = self.run_action(skill)
        logs = "".join(job["logs"])
        self.assertEqual(job["status"], "succeeded")
        self.assertIn("Log limit reached", logs)
        self.assertIn("测" * 4000, logs)
        self.assertNotIn("\ufffd", logs)
        self.assertLess(len(logs.encode("utf-8")), 263000)

    def test_original_third_party_executes_and_exports_stdout(self):
        source = Path(__file__).resolve().parents[1] / "examples" / "third-party" / "documents"
        fixture = source / "fixtures" / "sample.pdf"
        if not fixture.exists():
            self.skipTest("Third-party fixture is not available")
        capability = self.inspector.import_path(source)
        approval = self.jobs.prepare(capability["id"], "validate-documents", {"files": str(fixture), "json": True, "render_check": False})
        self.assertEqual(approval["command"][-1], "--json")
        job = self.wait(self.jobs.start(approval["approval_id"], True)["id"])
        self.assertEqual(job["status"], "succeeded", job)
        self.assertTrue(job["result"]["ok"])
        self.assertEqual(job["result"]["summary"]["passed"], 1)
        artifact = self.jobs.artifact(job["id"], "_skill2ui_stdout.json")
        self.assertEqual(json.loads(artifact.read_text(encoding="utf-8"))["status"], "ok")

    def test_exited_parent_cannot_leave_background_child(self):
        marker = self.base / "background-child-survived"
        child_code = f"import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text('BAD')"
        skill = self.action(f"import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', {child_code!r}], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nprint('parent finished')")
        job = self.run_action(skill)
        self.assertEqual(job["status"], "succeeded", job)
        time.sleep(1.1)
        self.assertFalse(marker.exists())

    def test_nonfinite_json_is_not_exposed_as_result(self):
        skill = self.action("print('{\"value\": NaN}')")
        job = self.run_action(skill)
        self.assertEqual(job["status"], "succeeded")
        self.assertNotIn("result", job)

    def test_artifact_hardlinks_not_exposed(self):
        secret = self.base / "secret"
        secret.write_text("private", encoding="utf-8")
        skill = self.action(f"import os\nos.link({str(secret)!r}, 'leaked.txt')")
        job = self.run_action(skill)
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(job["artifacts"], [])
        with self.assertRaises(FileNotFoundError):
            self.jobs.artifact(job["id"], "leaked.txt")

    def test_artifact_replaced_with_link_is_not_served(self):
        skill = self.action("from pathlib import Path\nPath('output.txt').write_text('good')")
        job = self.run_action(skill)
        artifact = self.jobs.artifact(job["id"], "output.txt")
        artifact.unlink()
        secret = self.base / "secret"
        secret.write_text("private", encoding="utf-8")
        os.link(secret, artifact)
        with self.assertRaises(FileNotFoundError):
            self.jobs.artifact(job["id"], "output.txt")

    def test_restart_marks_running_record_failed(self):
        identifier = "interrupted"
        directory = self.jobs.directory / identifier
        directory.mkdir()
        (directory / "job.json").write_text(json.dumps({"id": identifier, "status": "running", "created_at": "2026-01-01", "artifacts": []}), encoding="utf-8")
        recovered = JobManager(self.inspector, self.base / "data").get(identifier)
        self.assertEqual(recovered["status"], "failed")
        self.assertIn("restarted", recovered["error"])

    def test_unconfigured_action_is_blocked(self):
        (self.source / "scripts" / "run.py").write_text("import sys\nprint(sys.argv[1])", encoding="utf-8")
        skill = self.inspector.import_path(self.source)["id"]
        with self.assertRaisesRegex(ValueError, "not executable"):
            self.jobs.prepare(skill, "run", {"argument_1": "value"})


if __name__ == "__main__":
    unittest.main()
