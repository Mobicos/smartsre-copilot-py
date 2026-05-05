"""End-to-end smoke checks for a running SmartSRE Copilot instance."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"


class SmokeFailure(RuntimeError):
    """Raised when a smoke check fails."""


def wait_for_tcp(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise SmokeFailure(f"Timed out waiting for {host}:{port}")


def start_process(name: str, args: list[str]) -> subprocess.Popen[bytes]:
    LOG_DIR.mkdir(exist_ok=True)
    stdout = (LOG_DIR / f"smoke-{name}.out.log").open("ab")
    stderr = (LOG_DIR / f"smoke-{name}.err.log").open("ab")
    return subprocess.Popen(
        args,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
    )


def parse_sse_lines(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    data_lines: list[str] = []
    for line in lines:
        if not line:
            if data_lines:
                data = "\n".join(data_lines)
                data_lines = []
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    yield {"type": "raw", "data": data}
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())


def require_api_success(response: httpx.Response, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise SmokeFailure(f"{label} returned HTTP {response.status_code}: {response.text[:500]}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{label} returned non-object JSON payload: {payload!r}")
    if payload.get("code", response.status_code) >= 400:
        raise SmokeFailure(f"{label} returned error payload: {payload}")
    return cast(dict[str, Any], payload)


def check_health(client: httpx.Client) -> None:
    live = require_api_success(client.get("/health/live"), "live health")
    if live["data"]["status"] != "alive":
        raise SmokeFailure(f"Unexpected live health payload: {live}")

    health = require_api_success(client.get("/health"), "ready health")
    if health["data"]["status"] != "healthy":
        raise SmokeFailure(f"Unexpected health payload: {health}")


def check_ui(client: httpx.Client) -> None:
    response = client.get("/")
    if response.status_code != 200 or "SmartSRE Copilot" not in response.text:
        raise SmokeFailure("Web UI root did not return the SmartSRE page")

    script = client.get("/static/app.js")
    if script.status_code != 200 or "/api/chat" not in script.text:
        raise SmokeFailure("Frontend JavaScript did not load correctly")


def check_sessions(client: httpx.Client) -> None:
    payload = require_api_success(client.get("/api/chat/sessions"), "chat sessions")
    if not isinstance(payload.get("data"), list):
        raise SmokeFailure(f"chat sessions data is not a list: {payload}")


def check_upload_and_index(client: httpx.Client) -> tuple[str, str]:
    canary = f"SMOKE_CANARY_{int(time.time())}"
    document_text = (
        "# Smoke Test Knowledge\n\n"
        f"The launch smoke test marker is {canary}. "
        "If retrieval works, this exact marker can be found in the knowledge base.\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as file:
        file.write(document_text)
        temp_path = Path(file.name)

    try:
        with temp_path.open("rb") as file:
            response = client.post(
                "/api/upload",
                files={"file": (f"{canary}.md", file, "text/markdown")},
                timeout=30,
            )
        payload = require_api_success(response, "upload")
        task_id = payload["data"]["indexing"]["taskId"]

        deadline = time.monotonic() + 180
        last_payload: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            last_payload = require_api_success(
                client.get(f"/api/index_tasks/{task_id}"),
                "index task status",
            )
            status = last_payload["data"]["status"]
            if status == "completed":
                return task_id, canary
            if status == "failed_permanently":
                raise SmokeFailure(f"index task failed: {last_payload}")
            time.sleep(2)

        raise SmokeFailure(f"index task did not complete in time: {last_payload}")
    finally:
        temp_path.unlink(missing_ok=True)


def check_chat(client: httpx.Client, session_id: str) -> str:
    response = client.post(
        "/api/chat",
        json={"id": session_id, "question": "请只回复 CHAT_SMOKE_OK"},
        timeout=120,
    )
    payload = require_api_success(response, "chat")
    data = payload["data"]
    if not data.get("success") or not data.get("answer"):
        raise SmokeFailure(f"chat did not return a successful answer: {payload}")
    return str(data["answer"])


def check_stream_chat(client: httpx.Client, session_id: str) -> None:
    saw_content = False
    saw_done = False
    with client.stream(
        "POST",
        "/api/chat_stream",
        json={"id": session_id, "question": "请只回复 STREAM_SMOKE_OK"},
        timeout=120,
    ) as response:
        if response.status_code >= 400:
            raise SmokeFailure(f"chat stream returned HTTP {response.status_code}")
        for event in parse_sse_lines(response.iter_lines()):
            event_type = event.get("type")
            if event_type == "error":
                raise SmokeFailure(f"chat stream error: {event}")
            if event_type == "content":
                saw_content = True
            if event_type == "done":
                saw_done = True
                break
    if not saw_done or not saw_content:
        raise SmokeFailure("chat stream did not produce content and done events")


def check_knowledge_chat(client: httpx.Client, session_id: str, canary: str) -> None:
    response = client.post(
        "/api/chat",
        json={
            "id": session_id,
            "question": f"请使用知识库检索并回答：launch smoke test marker 是什么？只回答包含 {canary} 的一句话。",
        },
        timeout=120,
    )
    payload = require_api_success(response, "knowledge chat")
    answer = str(payload["data"].get("answer", ""))
    if canary not in answer:
        raise SmokeFailure(f"knowledge chat answer did not contain marker {canary}: {answer}")


def check_aiops(client: httpx.Client, session_id: str) -> str:
    run_id = ""
    saw_plan = False
    saw_complete = False
    with client.stream(
        "POST",
        "/api/aiops",
        json={"session_id": session_id},
        timeout=300,
    ) as response:
        if response.status_code >= 400:
            raise SmokeFailure(f"AIOps stream returned HTTP {response.status_code}")
        for event in parse_sse_lines(response.iter_lines()):
            run_id = str(event.get("run_id") or run_id)
            event_type = event.get("type")
            if event_type == "error":
                raise SmokeFailure(f"AIOps returned error event: {event}")
            if event_type == "plan":
                saw_plan = True
            if event_type == "complete":
                saw_complete = True
                break
    if not saw_plan or not saw_complete or not run_id:
        raise SmokeFailure("AIOps stream did not produce plan, complete, and run_id")

    run_payload = require_api_success(client.get(f"/api/aiops/runs/{run_id}"), "AIOps run")
    if run_payload["data"]["status"] != "completed":
        raise SmokeFailure(f"AIOps run is not completed: {run_payload}")

    events_payload = require_api_success(
        client.get(f"/api/aiops/runs/{run_id}/events"),
        "AIOps events",
    )
    if not events_payload["data"]:
        raise SmokeFailure("AIOps events list is empty")
    return run_id


def run_smoke(base_url: str, *, start_helpers: bool) -> None:
    processes: list[subprocess.Popen[bytes]] = []
    if start_helpers:
        processes.extend(
            [
                start_process("mcp-cls", [sys.executable, "mcp_servers/cls_server.py"]),
                start_process("mcp-monitor", [sys.executable, "mcp_servers/monitor_server.py"]),
                start_process("worker", [sys.executable, "-m", "app.worker"]),
            ]
        )
        wait_for_tcp("127.0.0.1", 8003, 30)
        wait_for_tcp("127.0.0.1", 8004, 30)
        time.sleep(2)

    checks: list[tuple[str, Any]] = []
    try:
        with httpx.Client(base_url=base_url, timeout=30) as client:
            session_id = f"smoke_{int(time.time())}"
            checks = [
                ("health", lambda: check_health(client)),
                ("ui", lambda: check_ui(client)),
                ("sessions", lambda: check_sessions(client)),
            ]
            for name, check in checks:
                check()
                print(f"PASS {name}")

            task_id, canary = check_upload_and_index(client)
            print(f"PASS upload_index task_id={task_id}")

            answer = check_chat(client, session_id)
            print(f"PASS chat answer={answer[:80]!r}")

            check_stream_chat(client, session_id)
            print("PASS chat_stream")

            check_knowledge_chat(client, session_id, canary)
            print(f"PASS knowledge_chat marker={canary}")

            run_id = check_aiops(client, session_id)
            print(f"PASS aiops run_id={run_id}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:9900"))
    parser.add_argument("--no-start-helpers", action="store_true")
    args = parser.parse_args()

    try:
        run_smoke(args.base_url, start_helpers=not args.no_start_helpers)
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
