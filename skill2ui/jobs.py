"""Approved local subprocesses, with bounded logs and durable execution records.

The permission prompt is a trust boundary. A subprocess is not an OS sandbox.
"""

from __future__ import annotations

import copy
import codecs
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import signal
import subprocess
import threading
import time

from .inspector import Inspector, _is_link, _json_write


LOG_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
ENVIRONMENT = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMDRIVE"}
SENSITIVE_NAME = re.compile(r"api[_ -]?key|password|secret|credential|(?:^|[_ -])token(?:[_ -]|$)|密钥|密码|令牌", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment(work: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() in ENVIRONMENT}
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "HOME": str(work), "USERPROFILE": str(work)})
    return environment


def _reject_constant(value: str):
    raise ValueError(f"Non-finite JSON constant: {value}")


class _LogRedactor:
    """Hold a short tail so a credential split across stdout chunks stays private."""
    def __init__(self, values):
        values = sorted({variant for value in values for variant in (value, json.dumps(value, ensure_ascii=False)[1:-1], json.dumps(value, ensure_ascii=True)[1:-1])}, key=len, reverse=True)
        self.pattern = re.compile("|".join(re.escape(value) for value in values)) if values else None
        self.maximum = max(map(len, values), default=1)
        self.pending = ""

    def redact(self, text):
        return self.pattern.sub("[REDACTED]", text) if self.pattern else text

    def feed(self, text, final=False):
        self.pending += text
        boundary = len(self.pending) if final else max(0, len(self.pending) - self.maximum + 1)
        if self.pattern and not final:
            for match in self.pattern.finditer(self.pending):
                if match.start() < boundary < match.end():
                    boundary = match.start()
                    break
        output, self.pending = self.pending[:boundary], self.pending[boundary:]
        return self.redact(output)

    def result(self, value):
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, list):
            return [self.result(item) for item in value]
        if isinstance(value, dict):
            return {self.redact(key): self.result(item) for key, item in value.items()}
        return value


class _WindowsProcessGroup:
    """A suspended launch closes the race before assigning the Windows Job Object."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.types = ctypes, wintypes
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                        ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class Limits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IO), ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]
        for name, args, result in (("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
                                   ("SetInformationJobObject", [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
                                   ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
                                   ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
                                   ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL)):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, process):
        ctypes, wintypes = self.ctypes, self.types
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        class ThreadEntry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("id", wintypes.DWORD),
                        ("owner", wintypes.DWORD), ("base_priority", wintypes.LONG), ("delta_priority", wintypes.LONG), ("flags", wintypes.DWORD)]
        for name, args, result in (("CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
                                   ("Thread32First", [wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
                                   ("Thread32Next", [wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
                                   ("OpenThread", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
                                   ("ResumeThread", [wintypes.HANDLE], wintypes.DWORD)):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner == process.pid:
                    thread = self.api.OpenThread(2, False, entry.id)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        self.api.CloseHandle(thread)
                found = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("Cannot resume the suspended action process")
        finally:
            self.api.CloseHandle(snapshot)

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _kill_tree(process: subprocess.Popen, group=None) -> None:
    if group is not None:
        group.terminate()
    elif os.name == "nt" and process.poll() is not None:
        return
    elif os.name == "nt":
        try:
            subprocess.run([str(Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


class JobManager:
    def __init__(self, inspector: Inspector, data_dir: Path):
        self.inspector = inspector
        self.directory = Path(data_dir).resolve() / "jobs"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._slots = threading.Semaphore(2)
        self._records, self._approvals, self._events, self._processes = {}, {}, {}, {}
        for path in sorted(self.directory.glob("*/job.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record["id"] != path.parent.name:
                    continue
                if record["status"] in {"queued", "running"}:
                    record.update(status="failed", error="Runtime restarted before completion; prepare and approve the action again.", finished_at=_now())
                    _json_write(path, record)
                self._records[record["id"]] = record
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def _save(self, record: dict) -> None:
        _json_write(self.directory / record["id"] / "job.json", record)

    def get(self, identifier: str) -> dict:
        with self._lock:
            if identifier not in self._records:
                raise FileNotFoundError("Job not found")
            return copy.deepcopy(self._records[identifier])

    def list(self) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(record) for record in sorted(self._records.values(), key=lambda item: item["created_at"], reverse=True)]

    def _command(self, capability: dict, action: dict, arguments: dict) -> tuple[list[str], dict, dict]:
        if not isinstance(arguments, dict) or any(not isinstance(key, str) for key in arguments):
            raise ValueError("Arguments must be an object")
        parameters = action["parameters"]
        if set(arguments) - {parameter["name"] for parameter in parameters}:
            raise ValueError("Unknown action argument")
        settings = self.inspector.action_config(capability["id"], action["id"])
        interpreter = shutil.which(action.get("interpreter", ""))
        if not interpreter:
            raise ValueError("Action interpreter or tool is not installed")
        # Windows may route a .cmd/.bat through cmd.exe even with shell=False.
        if Path(interpreter).suffix.lower() in {".cmd", ".bat"}:
            raise ValueError("Batch executables are not allowed; use a native executable")
        command = [str(Path(interpreter).resolve())]
        if "script" in action:
            script = (self.inspector.source_root(capability["id"]) / action["script"]).resolve()
            if not script.is_relative_to(self.inspector.source_root(capability["id"]).resolve()) or not script.is_file():
                raise ValueError("Registered script is unavailable")
            command.append(str(script))
        command.extend(settings["fixed_args"])
        normalized = {}
        for parameter in parameters:
            name, kind = parameter["name"], parameter["type"]
            if name not in arguments:
                if "default" in parameter:
                    value = parameter["default"]
                elif kind == "boolean":
                    value = settings["bindings"].get(name, "store_true") == "store_false"
                elif parameter["required"]:
                    raise ValueError(f"Required argument is missing: {name}")
                else:
                    continue
            else:
                value = arguments[name]
            if value is None or value == "":
                if parameter["required"]:
                    raise ValueError(f"Required argument is empty: {name}")
                if value is None or kind in {"file", "directory"}:
                    continue
            if kind == "boolean":
                if not isinstance(value, bool):
                    raise ValueError(f"{name} must be a boolean")
            elif kind in {"integer", "number"}:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{name} must be a finite {kind}")
                if kind == "integer" and not isinstance(value, int):
                    raise ValueError(f"{name} must be an integer")
            else:
                if not isinstance(value, str) or "\0" in value or len(value) > 32768:
                    raise ValueError(f"{name} must be a string without NUL bytes")
                if kind == "choice" and value not in parameter["choices"]:
                    raise ValueError(f"{name} is not an allowed choice")
                if kind in {"file", "directory"}:
                    path = Path(value).expanduser().resolve()
                    if (kind == "file" and not path.is_file()) or (kind == "directory" and not path.is_dir()):
                        raise ValueError(f"{name} must refer to an existing {kind}")
                    value = str(path)
            normalized[name] = value
            if kind == "boolean":
                behavior = settings["bindings"].get(name, "store_true")
                if value == (behavior == "store_true"):
                    command.append(parameter["flag"])
            elif parameter.get("positional"):
                if isinstance(value, str) and value.startswith("-"):
                    raise ValueError(f"{name} cannot begin with '-' in a positional argument")
                command.append(str(value))
            else:
                flag = parameter["flag"]
                if flag.startswith("--"):
                    command.append(f"{flag}={value}")
                else:
                    if isinstance(value, str) and value.startswith("-"):
                        raise ValueError(f"{name} cannot begin with '-' for a short flag")
                    command.extend([flag, str(value)])
        if sum(len(argument) + 3 for argument in command) > 32000:
            raise ValueError("Action command exceeds the 32,000-character limit")
        return command, normalized, settings

    def prepare(self, skill_id: str, action_id: str, arguments: dict) -> dict:
        capability = self.inspector.get(skill_id)
        action = next((item for item in capability["actions"] if item["id"] == action_id), None)
        if action is None:
            raise ValueError("Action not found")
        if action["status"] != "ready":
            raise ValueError("Action is not executable; resolve its dependencies or configuration first")
        digest = self.inspector.verify(skill_id)
        command, normalized, settings = self._command(capability, action, arguments)
        identifier = secrets.token_urlsafe(32)
        fingerprint = hashlib.sha256(json.dumps({"source": digest, "command": command, "arguments": normalized}, sort_keys=True).encode()).hexdigest()
        with self._lock:
            self._approvals = {key: value for key, value in self._approvals.items() if time.monotonic() - value["prepared_at"] < 900}
            self._approvals[identifier] = {"skill_id": skill_id, "action_id": action_id, "source_digest": digest, "command": command,
                                          "arguments": normalized, "settings": settings, "fingerprint": fingerprint, "prepared_at": time.monotonic()}
        permissions = sorted(set(action["permissions"] + ["execute_local_code", "write_job_directory"] + (["read_selected_files"] if any(parameter["type"] in {"file", "directory"} for parameter in action["parameters"]) else [])))
        return {"approval_id": identifier, "command": command, "permissions": permissions,
                "warning": "Approval runs the exact local command below. Imported code has your operating-system permissions and may read/write files or access the network. Execution is not an OS sandbox. Credential environment variables are removed; code can still read credentials on disk. Explicit credential arguments may appear in OS process tools; known values are redacted from saved commands and logs. Approve only trusted sources."}

    def start(self, approval_id: str, confirmed: bool) -> dict:
        if confirmed is not True:
            raise ValueError("Explicit user confirmation is required")
        with self._lock:
            approval = self._approvals.pop(approval_id, None)
            if approval is None or time.monotonic() - approval["prepared_at"] >= 900:
                raise ValueError("Approval is missing, expired, or already used; prepare again")
            if self.inspector.verify(approval["skill_id"]) != approval["source_digest"]:
                raise ValueError("Skill changed since approval")
            capability = self.inspector.get(approval["skill_id"])
            action = next(item for item in capability["actions"] if item["id"] == approval["action_id"])
            command, normalized, _ = self._command(capability, action, approval["arguments"])
            fingerprint = hashlib.sha256(json.dumps({"source": approval["source_digest"], "command": command, "arguments": normalized}, sort_keys=True).encode()).hexdigest()
            if fingerprint != approval["fingerprint"]:
                raise ValueError("Action command changed since approval")
            identifier = secrets.token_hex(12)
            sensitive_values = [value for name, value in normalized.items() if SENSITIVE_NAME.search(name) and isinstance(value, str) and value]
            approval["sensitive_values"] = sensitive_values
            redactor = _LogRedactor(sensitive_values)
            (self.directory / identifier / "work").mkdir(parents=True)
            record = {"id": identifier, "skill_id": approval["skill_id"], "action_id": approval["action_id"], "status": "queued",
                      "command": [redactor.redact(argument) for argument in command], "logs": [], "progress": 0, "artifacts": [], "created_at": _now()}
            self._records[identifier] = record
            self._events[identifier] = threading.Event()
            self._save(record)
            threading.Thread(target=self._run, args=(identifier, approval), daemon=True, name=f"skill2ui-{identifier}").start()
            return copy.deepcopy(record)

    def _run(self, identifier: str, approval: dict) -> None:
        event = self._events[identifier]
        work = self.directory / identifier / "work"
        process = None
        process_group = None
        with self._slots:
            with self._lock:
                record = self._records[identifier]
                if event.is_set():
                    self._events.pop(identifier, None)
                    return
                record.update(status="running", progress=0)
                self._save(record)
            try:
                if self.inspector.verify(approval["skill_id"]) != approval["source_digest"]:
                    raise ValueError("Skill source changed while the task was queued")
                if os.name == "nt":
                    process_group = _WindowsProcessGroup()
                options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | 0x4} if os.name == "nt" else {"start_new_session": True}
                process = subprocess.Popen(approval["command"], cwd=work, env=_environment(work), stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False, **options)
                if process_group:
                    process_group.attach_and_resume(process)
                with self._lock:
                    self._processes[identifier] = process
                output = queue.Queue(maxsize=128)
                def read_output():
                    try:
                        while True:
                            chunk = os.read(process.stdout.fileno(), 4096)
                            if not chunk:
                                break
                            while True:
                                try:
                                    output.put(chunk, timeout=0.1)
                                    break
                                except queue.Full:
                                    if event.is_set():
                                        return
                    except (OSError, ValueError):
                        pass
                    finally:
                        try:
                            output.put(None, timeout=0.1)
                        except queue.Full:
                            pass
                reader = threading.Thread(target=read_output, daemon=True)
                reader.start()
                deadline = time.monotonic() + approval["settings"]["timeout"]
                captured, truncated, ended, failure = 0, False, False, None
                decoder = codecs.getincrementaldecoder("utf-8")("replace")
                redactor = _LogRedactor(approval["sensitive_values"])
                cleaned_children = False
                while True:
                    if event.is_set():
                        _kill_tree(process, process_group)
                        break
                    if time.monotonic() >= deadline:
                        failure = f"Action exceeded its {approval['settings']['timeout']:g}-second timeout"
                        _kill_tree(process, process_group)
                        break
                    try:
                        chunk = output.get(timeout=0.1)
                    except queue.Empty:
                        chunk = b""
                    if chunk is None:
                        ended = True
                    elif chunk:
                        remaining = LOG_BYTES - captured
                        if remaining > 0:
                            portion = chunk[:remaining]
                            captured += len(portion)
                            with self._lock:
                                message = redactor.feed(decoder.decode(portion))
                                if message:
                                    record["logs"].append(message)
                                    self._save(record)
                        if len(chunk) > remaining and not truncated:
                            truncated = True
                            with self._lock:
                                record["logs"].append("\n[Log limit reached; further output is discarded.]\n")
                                self._save(record)
                    if process.poll() is not None:
                        if not cleaned_children:
                            _kill_tree(process, process_group)
                            cleaned_children = True
                        if ended or (not reader.is_alive() and output.empty()):
                            break
                process.wait(timeout=10)
                if process.stdout:
                    process.stdout.close()
                with self._lock:
                    trailing = "" if truncated else redactor.feed(decoder.decode(b"", final=True), final=True)
                    if trailing:
                        record["logs"].append(trailing)
                    if event.is_set():
                        record["status"] = "cancelled"
                    elif failure:
                        record.update(status="failed", error=failure)
                    elif process.returncode != 0:
                        record.update(status="failed", error=f"Process exited with status {process.returncode}")
                    else:
                        record.update(status="succeeded", progress=100)
                    self._artifacts(record, work, redactor)
                    record["finished_at"] = _now()
                    self._save(record)
            except Exception as exc:
                if process is not None:
                    _kill_tree(process, process_group)
                with self._lock:
                    record.update(status="cancelled" if event.is_set() else "failed", error=_LogRedactor(approval["sensitive_values"]).redact(str(exc)), finished_at=_now())
                    self._save(record)
            finally:
                if process_group:
                    process_group.close()
                with self._lock:
                    self._processes.pop(identifier, None)
                    self._events.pop(identifier, None)

    def _artifacts(self, record: dict, work: Path, redactor: _LogRedactor) -> None:
        if _is_link(work):
            record["logs"].append("\n[Output directory became a link; no artifacts are exposed.]\n")
            return
        artifacts, total, limited = [], 0, False
        for base, directories, names in os.walk(work, followlinks=False):
            directories[:] = [name for name in directories if not _is_link(Path(base) / name)]
            for name in sorted(names):
                path = Path(base) / name
                if _is_link(path) or not path.is_file() or path.stat().st_nlink > 1 or not path.resolve().is_relative_to(work):
                    continue
                size = path.stat().st_size
                total += size
                if len(artifacts) >= 100 or total > MAX_ARTIFACT_BYTES:
                    record["logs"].append("\n[Artifact listing limited to 100 files / 100 MiB.]\n")
                    limited = True
                    break
                artifacts.append({"name": path.relative_to(work).as_posix(), "size": size})
            if limited:
                break
        record["artifacts"] = artifacts
        result = work / "result.json"
        if record["status"] == "succeeded" and not _is_link(result) and result.is_file() and result.stat().st_nlink == 1 and result.stat().st_size <= 1024 * 1024:
            try:
                record["result"] = redactor.result(json.loads(result.read_text(encoding="utf-8"), parse_constant=_reject_constant))
            except (OSError, ValueError):
                pass
        elif record["status"] == "succeeded":
            try:
                record["result"] = redactor.result(json.loads("".join(record["logs"]), parse_constant=_reject_constant))
                captured = work / "_skill2ui_stdout.json"
                if not captured.exists() and not _is_link(captured) and len(artifacts) < 100:
                    captured.write_text(json.dumps(record["result"], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
                    record["artifacts"].append({"name": captured.name, "size": captured.stat().st_size})
            except (ValueError, TypeError):
                pass

    def cancel(self, identifier: str) -> dict:
        with self._lock:
            record = self._records.get(identifier)
            if record is None:
                raise FileNotFoundError("Job not found")
            if record["status"] in {"queued", "running"}:
                self._events[identifier].set()
                if record["status"] == "queued":
                    record.update(status="cancelled", finished_at=_now())
                    self._save(record)
            return copy.deepcopy(record)

    def artifact(self, identifier: str, name: str) -> Path:
        record = self.get(identifier)
        if name not in {artifact["name"] for artifact in record["artifacts"]}:
            raise FileNotFoundError("Artifact not found")
        work = self.directory / identifier / "work"
        path = work / name
        if _is_link(path) or any(_is_link(part) for part in path.parents) or not path.is_file() or path.stat().st_nlink > 1 or not path.resolve().is_relative_to(work):
            raise FileNotFoundError("Artifact path is no longer valid")
        return path
