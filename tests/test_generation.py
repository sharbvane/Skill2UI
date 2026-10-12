import json
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from skill2ui.generation import Generator, local_document, local_edit
from skill2ui.schema import UIDocument, calculate, evaluate


class GenerationTests(unittest.TestCase):
    def test_bill_correct_and_live(self):
        doc = local_document("生成多人 AA 费用计算器")
        self.assertEqual(evaluate(doc, {})["per_person"], 165)
        self.assertEqual(evaluate(doc, {"total": 900, "people": 3, "tip": 20})["per_person"], 360)
        for state in ({"people": 0}, {"people": 2.5}, {"total": -1}, {"tip": float("nan")}):
            with self.assertRaises(ValueError):
                evaluate(doc, state)

    def test_task_selection(self):
        for prompt, kind in [("销售数据分析", "data"), ("制定计划", "plan"), ("讲解系统结构", "diagram"), ("方案权重评估", "evaluation"), ("文件预览", "files"), ("自动化工作流", "workflow"), ("帮我创作诗歌", "workflow")]:
            with self.subTest(prompt=prompt):
                self.assertEqual(local_document(prompt).kind, kind)

    def test_edit_preserves_ids_and_changes_chart(self):
        doc = local_document("数据分析")
        ids = [item.id for item in doc.components]
        edited = local_edit(doc, "把柱状图改成折线图并改成深色主题")
        self.assertEqual(edited.id, doc.id)
        self.assertEqual(edited.theme, "dark")
        self.assertEqual([item.id for item in edited.components], ids)
        self.assertEqual(next(c.value for c in edited.components if c.id == "chart_type"), "line")
        self.assertEqual(edited.data, doc.data)

    def test_repeated_collapse_and_add(self):
        doc = local_edit(local_document("AA计算"), "折叠高级设置")
        doc = local_edit(doc, "增加一个参数滑块")
        doc = local_edit(doc, "折叠高级设置")
        UIDocument.model_validate(doc.model_dump())
        self.assertEqual(evaluate(doc, {"total": 100, "people": 2, "tip": 0})["per_person"], 50)
        doc = local_edit(doc, "删除新增滑块")
        self.assertFalse(any(c.id.startswith("parameter_") for c in doc.components[0].children))

    def test_no_executable_expressions(self):
        for expression in ["__import__('os').system('whoami')", "x[0]", "x.__class__", "2 ** 999999", "[x for x in y]", "1 +", "round(1, 99999)", "1/0"]:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                calculate(expression, {"x": 1})
        self.assertEqual(calculate("round(max(total, 0)/people, 2)", {"total": 10, "people": 3}), 3.33)

    def test_duplicate_and_unknown_components_rejected(self):
        raw = local_document("AA计算").model_dump()
        raw["components"].append(raw["components"][0])
        with self.assertRaises(ValidationError):
            UIDocument.model_validate(raw)
        raw["components"].pop()
        raw["components"][0]["type"] = "script"
        with self.assertRaises(ValidationError):
            UIDocument.model_validate(raw)

    def test_invalid_model_repaired_then_validated(self):
        calls = []
        raw = local_document("AA计算").model_dump()
        def response(request):
            calls.append(json.loads(request.content))
            content = "{bad" if len(calls) == 1 else json.dumps(raw)
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        client = httpx.Client(transport=httpx.MockTransport(response))
        generator = Generator()
        generator.configure("http://127.0.0.1:9999/v1", "test-model", "test-secret", 2)
        with patch("skill2ui.generation.httpx.Client", return_value=client):
            result = generator.generate("AA计算")
        self.assertEqual(result["mode"], "model")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("test-secret", json.dumps(result))

    def test_model_failure_is_truthful_fallback(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "secret"})))
        generator = Generator()
        generator.configure("https://example.com/v1", "model", "test-secret")
        with patch("skill2ui.generation.httpx.Client", return_value=client):
            result = generator.generate("AA计算")
        self.assertEqual(result["mode"], "local")
        self.assertIn("warning", result)
        self.assertNotIn("test-secret", json.dumps(result))

    def test_model_does_not_receive_credential_fields(self):
        doc = local_document("AA计算")
        raw = doc.model_dump()
        raw["components"].append({"id": "api_key", "type": "text", "label": "API Key", "value": "PRIVATE_TOKEN"})
        doc = UIDocument.model_validate(raw)
        requests = []
        def respond(request):
            requests.append(request.content.decode())
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(local_document("AA计算").model_dump())}}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        generator = Generator()
        generator.configure("http://127.0.0.1:9999/v1", "model", "test-secret")
        with patch("skill2ui.generation.httpx.Client", return_value=client):
            self.assertEqual(generator.generate("调整界面", doc, {"api_key": "PRIVATE_TOKEN", "total": 300})["mode"], "model")
        self.assertNotIn("PRIVATE_TOKEN", requests[0])

    def test_model_configuration_boundary(self):
        generator = Generator()
        for url in ["http://example.com/v1", "https://user:password@example.com", "file:///etc/passwd", "https://example.com?key=secret"]:
            with self.assertRaises(ValueError):
                generator.configure(url, "model", "key")


if __name__ == "__main__":
    unittest.main()
