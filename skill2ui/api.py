"""Loopback runtime. Browser content cannot register executors or bypass approval."""
import json
import os
import secrets
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import __version__
from .generation import Generator, private_field, skill_document
from .inspector import Inspector
from .jobs import JobManager
from .schema import UIDocument, evaluate

WEB = Path(__file__).parent / "web"
MAX_UPLOAD = 50 * 1024 * 1024


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD + 1024 * 1024 if scope["path"] in ("/api/uploads", "/api/skills/archive") else 2 * 1024 * 1024
        count = 0
        async def bounded_receive():
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > limit:
                raise HTTPException(status_code=413, detail="Request exceeds size limit")
            return message
        await self.app(scope, bounded_receive, send)


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Generate(Payload):
    prompt: str = Field(min_length=1, max_length=12000)
    document: UIDocument | None = None
    state: dict = Field(default_factory=dict)


class DocumentState(Payload):
    document: UIDocument
    state: dict = Field(default_factory=dict)


class ImportSkill(Payload):
    path: str | None = Field(default=None, max_length=4096)
    github: str | None = Field(default=None, max_length=2048)


class ModelConfig(Payload):
    base_url: str = Field(max_length=2048)
    model: str = Field(max_length=200)
    api_key: str = Field(default="", max_length=2000)
    timeout: float = Field(default=45, ge=1, le=180)


class Prepare(Payload):
    skill_id: str = Field(max_length=100)
    action_id: str = Field(max_length=100)
    arguments: dict = Field(default_factory=dict)


class Start(Payload):
    approval_id: str = Field(max_length=100)
    confirmed: bool = False


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def create_app(data_dir=None):
    directory = Path(data_dir or os.getenv("SKILL2UI_DATA_DIR", ".skill2ui")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    inspector, generator = Inspector(directory), Generator()
    jobs = JobManager(inspector, directory)
    app = FastAPI(title="Skill2UI", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.state.inspector, app.state.jobs, app.state.generator = inspector, jobs, generator
    app.state.directory = directory

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.url.hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            return JSONResponse({"detail": "Only loopback hosts are supported"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "Foreign origins are not allowed"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests are not allowed"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        limit = MAX_UPLOAD + 1024 * 1024 if request.url.path in ("/api/uploads", "/api/skills/archive") else 2 * 1024 * 1024
        if length < 0 or length > limit:
            return JSONResponse({"detail": "Request exceeds size limit"}, status_code=413)
        if request.url.path.startswith("/api/") and request.url.path != "/api/bootstrap":
            supplied = request.headers.get("x-skill2ui-token", "")
            if request.method in ("GET", "HEAD") and not supplied:
                supplied = request.cookies.get("skill2ui_session", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Open this runtime first; session token is required"}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-src blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)[:1000]}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Requested file or resource does not exist"}, status_code=404)

    @app.exception_handler(PermissionError)
    async def forbidden(request, exc):
        return JSONResponse({"detail": str(exc)[:1000]}, status_code=403)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        # Pydantic errors otherwise echo API keys or other supplied credentials.
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/")
    def index():
        return FileResponse(WEB / "index.html")

    @app.get("/api/bootstrap")
    def bootstrap():
        documents = []
        for path in sorted((directory / "documents").glob("*.json")):
            try:
                documents.append(json.loads(path.read_text(encoding="utf-8"))["document"])
            except (ValueError, KeyError, OSError):
                continue
        response = JSONResponse(dict(token=token, version=__version__, skills=inspector.list(), documents=documents, model=generator.public_config()))
        response.set_cookie("skill2ui_session", token, httponly=True, samesite="strict")
        return response

    @app.post("/api/generate")
    def generate(body: Generate):
        return generator.generate(body.prompt, body.document, body.state)

    @app.post("/api/generate/stream")
    def generate_stream(body: Generate):
        def events():
            yield 'event: status\ndata: {"message":"正在规划界面"}\n\n'
            result = generator.generate(body.prompt, body.document, body.state)
            for item in result["document"]["components"]:
                yield "event: component\ndata: " + json.dumps(item, ensure_ascii=False) + "\n\n"
            yield "event: document\ndata: " + json.dumps(result, ensure_ascii=False) + "\n\n"
        return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.post("/api/evaluate")
    def evaluate_ui(body: DocumentState):
        return {"metrics": evaluate(body.document, body.state)}

    @app.post("/api/documents")
    def save(body: DocumentState):
        saved = body.model_dump()
        saved["state"] = {key: value for key, value in saved["state"].items() if not private_field(key)}
        def redact(items):
            for item in items:
                if private_field(item["id"]):
                    item["value"] = ""
                redact(item.get("children", []))
        redact(saved["document"]["components"])
        for action in saved["document"]["actions"]:
            for parameter in action.get("parameters", []):
                if private_field(str(parameter.get("name", ""))):
                    parameter.pop("default", None)
        atomic_json(directory / "documents" / (body.document.id + ".json"), saved)
        return {"id": body.document.id}

    @app.get("/api/documents/{id}")
    def load(id: str):
        if not id.replace("_", "").replace("-", "").isalnum() or len(id) > 64:
            raise ValueError("Invalid document ID")
        raw = json.loads((directory / "documents" / (id + ".json")).read_text(encoding="utf-8"))
        DocumentState.model_validate(raw)
        return raw

    @app.post("/api/model")
    def configure(body: ModelConfig):
        return generator.configure(**body.model_dump())

    @app.get("/api/skills")
    def skills():
        return inspector.list()

    @app.get("/api/skills/discover")
    def discover():
        roots = [Path.home() / ".codex/skills", Path.home() / ".agents/skills", Path.home() / ".claude/skills"]
        found = []
        for root in roots:
            if root.is_dir():
                for path in root.glob("*/SKILL.md"):
                    found.append({"name": path.parent.name, "path": str(path.parent)})
        return found[:300]

    @app.post("/api/skills/import")
    def import_skill(body: ImportSkill):
        if bool(body.path) == bool(body.github):
            raise ValueError("Specify one local path or GitHub URL")
        return inspector.import_github(body.github) if body.github else inspector.import_path(body.path)

    async def receive(file: UploadFile, target: Path):
        size = 0
        try:
            with target.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(status_code=413, detail="File exceeds 50 MB")
                    output.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return size

    @app.post("/api/skills/archive")
    async def archive(file: UploadFile = File(...)):
        if not (file.filename or "").lower().endswith(".zip"):
            raise ValueError("Import a .zip Skill archive")
        with tempfile.TemporaryDirectory(prefix="skill2ui-import-") as temporary:
            path = Path(temporary) / "skill.zip"
            await receive(file, path)
            return await run_in_threadpool(inspector.import_archive, path)

    @app.post("/api/skills/{id}/gui")
    def skill_gui(id: str):
        return {"document": skill_document(inspector.get(id)).model_dump()}

    @app.post("/api/uploads")
    async def upload(file: UploadFile = File(...)):
        name = Path((file.filename or "file").replace("\\", "/")).name
        name = "".join(c for c in name if c.isalnum() or c in "._- ")[:150] or "file"
        parent = directory / "uploads" / uuid.uuid4().hex
        parent.mkdir(parents=True)
        path = parent / name
        size = await receive(file, path)
        return dict(path=str(path), name=name, size=size)

    @app.post("/api/actions/prepare")
    def prepare(body: Prepare):
        return jobs.prepare(**body.model_dump())

    @app.post("/api/jobs")
    def start(body: Start):
        return jobs.start(**body.model_dump())

    @app.get("/api/jobs")
    def list_jobs():
        return jobs.list()

    @app.get("/api/jobs/{id}")
    def get_job(id: str):
        return jobs.get(id)

    @app.post("/api/jobs/{id}/cancel")
    def cancel(id: str):
        return jobs.cancel(id)

    @app.get("/api/artifacts/{job_id}/{name:path}")
    def artifact(job_id: str, name: str):
        path = jobs.artifact(job_id, name)
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
