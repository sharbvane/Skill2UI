"""Deterministic task layouts and an optional, validated model planner."""
import copy
import json
import os
import re
import uuid
from urllib.parse import urlparse

import httpx

from .schema import UIDocument


def component(id, type, label, **fields):
    return dict(id=id, type=type, label=label, **fields)


def private_field(name):
    return bool(re.search(r"api[_ -]?key|password|secret|credential|authorization|(?:^|[_-])(?:access[_-]?|auth[_-]?)?token$", name, re.I))


def local_document(prompt):
    p = prompt.lower()
    c = component
    title, description, kind, data = "多人 AA 计算器", "调整金额、人数和小费，实时计算每人应付。", "calculator", []
    components = [c("total", "number", "总金额", value=600, min=0, max=1e12, step=0.01), c("people", "number", "人数", value=4, min=1, max=10000, step=1), c("tip", "slider", "小费比例 (%)", value=10, min=0, max=100, step=1), c("per_person", "metric", "每人应付", expression="round(total * (1 + tip / 100) / people, 2)"), c("grand_total", "metric", "含小费总额", expression="round(total * (1 + tip / 100), 2)")]
    if re.search(r"数据|图表|柱状|折线|销售|data|chart|csv|分析", p):
        title, description, kind = "数据探索面板", "编辑数据，筛选项目，在表格和图表之间切换。", "data"
        data = [{"label": "一月", "value": 120}, {"label": "二月", "value": 180}, {"label": "三月", "value": 145}, {"label": "四月", "value": 260}, {"label": "五月", "value": 210}, {"label": "六月", "value": 320}]
        components = [c("filter", "text", "筛选项目", value=""), c("chart_type", "select", "图表类型", options=["bar", "line"], value="bar"), c("view", "select", "展示方式", options=["chart", "table"], value="chart"), c("dataset", "textarea", "数据 (CSV: label,value)", value="label,value\n" + "\n".join(f"{r['label']},{r['value']}" for r in data)), c("visualization", "chart", "数据比较"), c("data_table", "table", "数据明细")]
    elif re.search(r"方案|评分|权重|评估|evaluate|decision|compare", p):
        title, description, kind = "方案评估", "调整权重，比较成本、质量与交付速度。示例评分可在数据区修改。", "evaluation"
        components = [c("cost", "slider", "成本权重", value=40, min=0, max=100, step=1), c("quality", "slider", "质量权重", value=35, min=0, max=100, step=1), c("speed", "slider", "速度权重", value=25, min=0, max=100, step=1), c("scores", "textarea", "方案评分 (CSV: label,cost,quality,speed)", value="label,cost,quality,speed\n方案 A,90,65,80\n方案 B,60,95,70\n方案 C,75,80,95"), c("ranking", "chart", "加权得分")]
        data = [{"label": "方案 A", "cost": 90, "quality": 65, "speed": 80}, {"label": "方案 B", "cost": 60, "quality": 95, "speed": 70}, {"label": "方案 C", "cost": 75, "quality": 80, "speed": 95}]
    elif re.search(r"计划|日程|时间线|plan|schedule|timeline", p):
        title, description, kind = "行动计划", "编辑步骤与时间，勾选完成的事项。", "plan"
        components = [c("steps", "textarea", "计划步骤（每行一项）", value="09:00 明确目标\n10:00 收集资料\n14:00 执行任务\n17:00 复盘结果"), c("timeline", "timeline", "任务时间线")]
    elif re.search(r"原理|结构|讲解|流程图|diagram|explain|architecture", p):
        title, description, kind = "交互式结构图", "点击步骤查看说明，编辑结构以组织自己的讲解。", "diagram"
        components = [c("steps", "textarea", "结构步骤（每行：名称 | 说明）", value="输入 | 用户描述需求或导入 Skill\n理解 | 识别输入、输出及可用能力\n界面 | 生成经过校验的组件\n执行 | 用户确认后执行已注册的操作\n结果 | 展示真实结果与执行记录"), c("structure", "diagram", "从意图到结果")]
    elif re.search(r"文件|pdf|视频|图片|file|upload|media", p):
        title, description, kind = "文件工作台", "导入文件并预览。处理文件时，导入对应 Skill 以连接真实操作。", "files"
        components = [c("input_file", "file", "选择文件"), c("file_preview", "media", "文件预览"), c("notes", "textarea", "处理要求", value=prompt)]
    elif re.search(r"工作流|自动化|任务|workflow|automation", p):
        title, description, kind = "工作流控制台", "导入一个可执行 Skill，配置操作并查看真实日志与结果。", "workflow"
        components = [c("workflow", "diagram", "任务流程", value=["选择 Skill", "配置参数", "确认权限", "执行任务", "查看结果"]), c("run_log", "log", "执行日志"), c("run_progress", "progress", "任务状态", value=0)]
    # The local planner covers explicit task families; unfamiliar requests require a configured model.
    known = re.search(r"aa|费用|金额|人数|小费|计算|split|bill|calculator|数据|图表|销售|data|chart|csv|分析|方案|评分|权重|评估|evaluate|decision|compare|计划|日程|时间线|plan|schedule|timeline|原理|结构|讲解|流程图|diagram|explain|architecture|文件|pdf|视频|图片|file|upload|media|工作流|自动化|任务|workflow|automation", p)
    if not known:
        title, description, kind = "需求向导", "当前使用本地模板。配置模型可为这项需求规划专用界面；也可导入相关 Skill。", "workflow"
        components = [c("request", "textarea", "需求描述", value=prompt), c("next_steps", "timeline", "下一步", value=["配置 OpenAI-compatible 模型", "或导入相关 Skill", "生成并检查界面"])]
    return UIDocument(id="ui_" + uuid.uuid4().hex[:12], title=title, description=description, kind=kind, components=components, data=data)


def local_edit(document, prompt):
    d = document.model_dump()
    p = prompt.lower()
    def items(components):
        for item in components:
            yield item
            yield from items(item.get("children", []))
    themes = re.findall(r"深色|暗色|dark|浅色|亮色|light", p)
    if themes:
        d["theme"] = "dark" if themes[-1] in ("深色", "暗色", "dark") else "light"
    charts = re.findall(r"折线|line|柱状|bar", p)
    for item in items(d["components"]):
        if item["id"] == "chart_type" and charts:
            item["value"] = "line" if charts[-1] in ("折线", "line") else "bar"
    if re.search(r"增加.*滑块|add.*slider", p):
        identifier = "parameter_" + str(len(d["components"]))
        d["components"].append(component(identifier, "slider", "新增参数", value=50, min=0, max=100, step=1))
    if re.search(r"预览|preview", p) and not any(i["type"] == "media" for i in items(d["components"])):
        d["components"].extend([component("preview_input", "file", "预览文件"), component("preview_media", "media", "文件预览")])
    if re.search(r"折叠|collapse|高级", p):
        inputs = [i for i in d["components"] if i["type"] in ("text", "number", "slider", "select", "textarea")]
        d["components"] = [i for i in d["components"] if i not in inputs]
        if inputs:
            group = next((i for i in d["components"] if i["id"] == "advanced"), None)
            if group:
                group["children"].extend(inputs)
            else:
                d["components"].insert(0, component("advanced", "group", "高级设置", children=inputs))
    if re.search(r"删除.*滑块|remove.*slider", p):
        def remove(components):
            remaining = [i for i in components if not i["id"].startswith("parameter_")]
            for item in remaining:
                item["children"] = remove(item.get("children", []))
            return remaining
        d["components"] = remove(d["components"])
    return UIDocument.model_validate(d)


class Generator:
    def __init__(self):
        self.key = os.getenv("SKILL2UI_API_KEY", "")
        self.base_url = os.getenv("SKILL2UI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("SKILL2UI_MODEL", "")
        self.timeout = 45

    def configure(self, base_url, model, api_key, timeout=45):
        parsed = urlparse(base_url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError("Use a base URL without credentials, query or fragment")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")):
            raise ValueError("Use HTTPS, or HTTP for a local model")
        if not model.strip() or not 1 <= timeout <= 180:
            raise ValueError("Specify a model and a timeout from 1 to 180 seconds")
        self.base_url, self.model, self.key, self.timeout = base_url.rstrip("/"), model.strip(), api_key, timeout
        return self.public_config()

    def public_config(self):
        return dict(configured=bool(self.model), base_url=self.base_url, model=self.model, timeout=self.timeout)

    def generate(self, prompt, document=None, state=None):
        if not prompt.strip() or len(prompt) > 12000:
            raise ValueError("Enter a request of 1–12000 characters")
        fallback = lambda: local_edit(document, prompt) if document else local_document(prompt)
        if not self.model:
            return dict(document=fallback().model_dump(), mode="local")
        instruction = "You plan an interactive UI. Return one JSON UIDocument only. Never emit HTML, code, URLs, shell commands, actions, skill_id, or external tool instructions. Only supported component types and safe arithmetic expressions. Preserve existing component IDs and data on edits. Use Chinese labels for Chinese requests. Data should be explicit example data unless supplied. Schema: " + json.dumps(UIDocument.model_json_schema(), ensure_ascii=False)
        current = document.model_dump() if document else None
        if current:
            current["actions"] = []
            current.pop("skill_id", None)
            def redact(items):
                for item in items:
                    if private_field(item["id"]):
                        item["value"] = ""
                    redact(item.get("children", []))
            redact(current["components"])
        public_state = {key: value for key, value in (state or {}).items() if not private_field(key)}
        messages = [{"role": "system", "content": instruction}, {"role": "user", "content": json.dumps(dict(request=prompt, current=current, state=public_state), ensure_ascii=False)}]
        headers = {"Authorization": "Bearer " + self.key} if self.key else {}
        warning = "模型生成失败，已使用本地模板。检查模型、网络与配置。"
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
                for attempt in range(2):
                    response = client.post(self.base_url + "/chat/completions", headers=headers, json={"model": self.model, "messages": messages, "response_format": {"type": "json_object"}, "max_tokens": 5000})
                    if response.status_code in (400, 422) and attempt == 0:
                        # Some compatible endpoints lack JSON mode; the next request keeps validation.
                        response = client.post(self.base_url + "/chat/completions", headers=headers, json={"model": self.model, "messages": messages, "max_tokens": 5000})
                    response.raise_for_status()
                    if len(response.content) > 250_000:
                        raise ValueError("Model response is too large")
                    content = response.json()["choices"][0]["message"]["content"]
                    try:
                        raw = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip()))
                        raw["actions"] = []
                        raw.pop("skill_id", None)
                        parsed = UIDocument.model_validate(raw)
                        if document:
                            parsed.id = document.id
                            # A model cannot replace an imported skill's registered actions.
                            parsed.skill_id, parsed.actions = document.skill_id, document.actions
                        return dict(document=parsed.model_dump(), mode="model")
                    except (ValueError, TypeError, SyntaxError):
                        messages.append({"role": "assistant", "content": content[:20000]})
                        messages.append({"role": "user", "content": "Invalid UI schema. Return valid JSON with supported types, unique IDs and arithmetic expressions only."})
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            pass
        return dict(document=fallback().model_dump(), mode="local", warning=warning)


def skill_document(capability):
    components = [component("skill_description", "text", "使用说明", value=capability["description"])]
    # Parameter fields are rendered from the registered Action Schema once, without a duplicate UI tree.
    components.extend([component("job_progress", "progress", "任务状态", value=0), component("job_log", "log", "执行日志")])
    return UIDocument(id="skill_" + capability["id"][:32] + "_" + capability["source"]["sha256"][:16], title=capability["name"], description=capability["description"], kind="skill", skill_id=capability["id"], components=components, actions=capability["actions"])
