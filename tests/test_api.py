import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from skill2ui.api import create_app


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(self.temp.name), base_url="http://127.0.0.1")
        self.bootstrap = self.client.get("/api/bootstrap").json()
        self.client.headers["X-Skill2UI-Token"] = self.bootstrap["token"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_boundary(self):
        self.assertEqual(self.client.post("/api/generate", json={"prompt": "AA"}, headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/bootstrap", headers={"Host": "evil.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/generate", json={"prompt": "AA"}, headers={"X-Skill2UI-Token": "wrong"}).status_code, 403)
        self.assertEqual(self.client.get("/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_chunked_request_is_bounded(self):
        response = self.client.post("/api/generate", content=iter([b'{"prompt":"', b"a" * (2 * 1024 * 1024), b'"}']), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413, response.text[:300])

    def test_generate_evaluate_save_restore(self):
        result = self.client.post("/api/generate", json={"prompt": "AA费用计算器"})
        self.assertEqual(result.status_code, 200, result.text)
        doc = result.json()["document"]
        body = {"document": doc, "state": {"total": 300, "people": 3, "tip": 10}}
        self.assertEqual(self.client.post("/api/evaluate", json=body).json()["metrics"]["per_person"], 110)
        self.assertEqual(self.client.post("/api/documents", json=body).status_code, 200)
        self.assertEqual(self.client.get("/api/documents/" + doc["id"]).json()["state"], body["state"])

    def test_stream_and_invalid_schema(self):
        response = self.client.post("/api/generate/stream", json={"prompt": "数据分析"})
        self.assertIn("event: component", response.text)
        self.assertIn("event: document", response.text)
        doc = self.client.post("/api/generate", json={"prompt": "AA"}).json()["document"]
        doc["components"][0]["type"] = "script"
        self.assertEqual(self.client.post("/api/evaluate", json={"document": doc}).status_code, 422)

    def test_model_secret_not_echoed_or_saved(self):
        result = self.client.post("/api/model", json={"base_url": "https://example.com/v1", "model": "test", "api_key": "PRIVATE_TOKEN", "timeout": 181})
        self.assertEqual(result.status_code, 422)
        self.assertNotIn("PRIVATE_TOKEN", result.text)
        result = self.client.post("/api/model", json={"base_url": "https://example.com/v1", "model": "test", "api_key": "PRIVATE_TOKEN"})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("PRIVATE_TOKEN", self.client.get("/api/bootstrap").text)
        self.assertFalse(any(Path(self.temp.name).rglob("*PRIVATE_TOKEN*")))

    def test_action_credentials_are_session_only(self):
        doc = self.client.post("/api/generate", json={"prompt": "AA"}).json()["document"]
        doc["components"].append({"id": "api_key", "type": "text", "label": "API Key", "value": "PRIVATE_TOKEN"})
        doc["actions"] = [{"id": "configured", "parameters": [{"name": "password", "default": "PRIVATE_TOKEN"}]}]
        response = self.client.post("/api/documents", json={"document": doc, "state": {"api_key": "PRIVATE_TOKEN", "total": 250}})
        self.assertEqual(response.status_code, 200)
        restored = self.client.get("/api/documents/" + doc["id"])
        self.assertNotIn("PRIVATE_TOKEN", restored.text)
        self.assertEqual(restored.json()["state"], {"total": 250})

    def test_upload_path_sanitized_and_download_boundary(self):
        result = self.client.post("/api/uploads", files={"file": ("../../secret.txt", b"hello", "text/plain")})
        self.assertEqual(result.status_code, 200, result.text)
        path = Path(result.json()["path"])
        self.assertTrue(path.is_relative_to(Path(self.temp.name).resolve()))
        self.assertEqual(path.name, "secret.txt")
        self.assertEqual(path.read_text(), "hello")
        self.assertIn("object-src 'none'", self.client.get("/").headers["Content-Security-Policy"])


if __name__ == "__main__":
    unittest.main()
