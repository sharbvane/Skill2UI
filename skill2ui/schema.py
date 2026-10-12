"""The only UI language the runtime accepts; it never contains executable code."""
import ast
import math
import operator
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    type: Literal["text", "number", "slider", "select", "file", "textarea", "metric", "table", "chart", "timeline", "diagram", "log", "progress", "media", "action", "group"]
    label: str = Field(max_length=500)
    value: Any = None
    options: list[str] = Field(default_factory=list, max_length=100)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    expression: str | None = Field(default=None, max_length=300)
    children: list["Component"] = Field(default_factory=list, max_length=50)


class UIDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["1.0"] = "1.0"
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    kind: Literal["calculator", "data", "diagram", "plan", "files", "evaluation", "workflow", "skill"]
    theme: Literal["light", "dark"] = "light"
    components: list[Component] = Field(max_length=50)
    data: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    skill_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique_components(self):
        ids = set()
        def visit(items, depth=0):
            if depth > 4:
                raise ValueError("Component nesting exceeds four levels")
            for item in items:
                if item.id in ids or len(ids) >= 100:
                    raise ValueError("Component IDs must be unique; at most 100 components")
                ids.add(item.id)
                if item.expression:
                    parse_expression(item.expression)
                if item.min is not None and item.max is not None and item.min > item.max:
                    raise ValueError("Minimum must not exceed maximum")
                visit(item.children, depth + 1)
        visit(self.components)
        return self


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod}
FUNCTIONS = {"round": round, "min": min, "max": max, "abs": abs}


def parse_expression(expression):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid arithmetic expression") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 80:
        raise ValueError("Expression is too complex")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call, ast.USub, ast.UAdd, *OPS)
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError("Only arithmetic, variables, round/min/max/abs are allowed")
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or not math.isfinite(node.value) or abs(node.value) > 1e15):
            raise ValueError("Invalid numeric constant")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords or not 1 <= len(node.args) <= 8):
            raise ValueError("Invalid arithmetic function")
    return tree


def calculate(expression, values):
    def resolve(node):
        if isinstance(node, ast.Constant):
            result = node.value
        elif isinstance(node, ast.Name):
            raw = values.get(node.id)
            if isinstance(raw, bool) or raw is None:
                raise ValueError(f"Missing numeric input: {node.id}")
            result = float(raw)
        elif isinstance(node, ast.BinOp):
            result = OPS[type(node.op)](resolve(node.left), resolve(node.right))
        elif isinstance(node, ast.UnaryOp):
            result = (-1 if isinstance(node.op, ast.USub) else 1) * resolve(node.operand)
        elif isinstance(node, ast.Call):
            args = [resolve(arg) for arg in node.args]
            if node.func.id == "round" and len(args) == 2:
                if not args[1].is_integer() or abs(args[1]) > 12:
                    raise ValueError("Round precision must be an integer from -12 to 12")
                args[1] = int(args[1])
            result = FUNCTIONS[node.func.id](*args)
        else:
            raise ValueError("Invalid expression")
        result = float(result)
        if not math.isfinite(result) or abs(result) > 1e15:
            raise ValueError("Calculation exceeds supported range")
        return result
    try:
        return resolve(parse_expression(expression).body)
    except (ZeroDivisionError, TypeError, OverflowError) as exc:
        raise ValueError("Check inputs: division by zero or invalid arithmetic") from exc


def evaluate(document: UIDocument, state: dict):
    values = {}
    def walk(items):
        for item in items:
            yield item
            yield from walk(item.children)
    components = list(walk(document.components))
    for item in components:
        values[item.id] = state.get(item.id, item.value)
        if item.type in ("number", "slider"):
            try:
                value = float(values[item.id])
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{item.label}: enter a number") from exc
            if not math.isfinite(value) or (item.min is not None and value < item.min) or (item.max is not None and value > item.max):
                raise ValueError(f"{item.label}: input outside allowed range")
            if item.step == 1 and not value.is_integer():
                raise ValueError(f"{item.label}: enter a whole number")
            values[item.id] = value
    return {item.id: calculate(item.expression, values) for item in components if item.type == "metric" and item.expression}
