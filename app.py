#!/usr/bin/env python3
"""Evaluator adapter. Early valid output + an external worker deadline protect every query."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

from agent.output import atomic_json, output_payload, output_path
from agent.types import read_budget
from agent.processes import run_bounded,stop_started_process
import secrets

ROOT = Path(__file__).resolve().parent


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                return True  # Unknown state is not permission to steal a lock.
            return code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def run_query(query, url="", qid=None, directory=None, profile="minimal", diagnostics=False):
    directory = directory or os.getenv("APERTURE_OUTPUT", "/app/output" if os.name != "nt" else str(ROOT / "output"))
    path = output_path(directory, qid)
    result = {"answer": "", "sources": [], "confidence": 0, "reason": "worker_not_finished"}
    atomic_json(path, output_payload(result, profile))
    started = time.monotonic()
    if not isinstance(query,str) or not isinstance(url,str):
        result['reason']='invalid_input_types'
        if diagnostics:atomic_json(path.with_name(path.stem+'.trace.json'),result)
        return output_payload(result,profile)
    hard_limit = min(27, max(0.2, read_budget()) + 1)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        process = run_bounded([sys.executable, "-m", "agent.worker"],
            input=json.dumps({"query": query, "url": url}, ensure_ascii=False).encode("utf-8"),
            cwd=ROOT, env=env, timeout=hard_limit)
        if process.returncode == 0:
            parsed = json.loads(process.stdout)
            if isinstance(parsed, dict) and isinstance(parsed.get("answer"), str) and isinstance(parsed.get("sources"), list):
                result = parsed
            else:
                result["reason"] = "malformed_worker_result"
        else:
            result["reason"] = "worker_failure"
            result["error"] = process.stderr.decode("utf-8", "replace")[-2000:]
    except subprocess.TimeoutExpired:
        result["reason"] = "worker_watchdog"
    except (OSError, ValueError) as exc:
        result["reason"] = type(exc).__name__
        result["error"] = str(exc)
    result["seconds"] = time.monotonic() - started
    final = output_payload(result, profile)
    atomic_json(path, final)
    if diagnostics:
        atomic_json(path.with_name(path.stem + ".trace.json"), result)
    return final


def warmup(wait=540, autostart=True, return_child=False):
    endpoint = os.getenv("APERTURE_MODEL_URL", "http://127.0.0.1:8765").rstrip("/") + "/health"
    limit = time.monotonic() + wait
    child = None
    lock_path = None
    lock_owner = None
    completed = False
    token = ""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    state = Path(os.getenv("APERTURE_STATE", str(ROOT / ".state") if os.name == "nt" else "/tmp/aperture"))
    try:
        while time.monotonic() < limit:
            data = None
            try:
                with opener.open(endpoint, timeout=min(2, max(0.01, limit-time.monotonic()))) as response:
                    data = json.load(response)
            except (OSError, ValueError):
                pass
            if isinstance(data, dict) and data.get("ready"):
                if child is not None and data.get("startup_token") != token:
                    raise RuntimeError("The model port was occupied by another instance during startup")
                completed = True
                return (data, child) if return_child else data
            if child is not None and child.poll() is not None:
                raise RuntimeError(f"Resident selector startup failed (exit {child.returncode}); see {state / 'model.log'}")
            if autostart and child is None:
                state.mkdir(parents=True, exist_ok=True, mode=0o700)
                candidate = state / "startup.lock"
                try:
                    fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                except FileExistsError:
                    try:
                        age = time.time() - candidate.stat().st_mtime
                        text = candidate.read_text(encoding="utf-8")
                        owner = int(text) if text.strip().isdigit() else 0
                        if age > 2 and owner > 0 and not process_alive(owner) or age > 540 and owner == 0:
                            candidate.unlink(missing_ok=True)
                    except (OSError, ValueError):
                        time.sleep(0.05)
                else:
                    lock_path, lock_owner = candidate, os.getpid()
                    with os.fdopen(fd, "w", encoding="utf-8") as marker:
                        marker.write(str(lock_owner))
                    log = state / "model.log"
                    if log.exists() and log.stat().st_size > 2_000_000:
                        log.replace(state / "model.previous.log")
                    token = secrets.token_hex(16)
                    environment = dict(os.environ, APERTURE_STARTUP_TOKEN=token)
                    with log.open("ab") as stream:
                        child = subprocess.Popen([sys.executable, "-m", "agent.model_server"], cwd=ROOT,
                            env=environment, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                            start_new_session=os.name != "nt",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    lock_owner = child.pid
                    candidate.write_text(str(lock_owner), encoding="utf-8")
            time.sleep(min(0.25, max(0, limit-time.monotonic())))
        raise RuntimeError("Resident selector was not inference-ready within startup budget")
    finally:
        if child is not None and not completed:
            stop_started_process(child)
        if lock_path:
            try:
                if lock_path.read_text(encoding="utf-8") == str(lock_owner):
                    lock_path.unlink(missing_ok=True)
            except OSError:
                pass


def serve_resident():
    # All shipping entry points share the warmup lock. A simultaneous --warmup
    # cannot start a second model while the default container command is loading.
    data, child = warmup(return_child=True)
    print(json.dumps(data, ensure_ascii=True), flush=True)
    try:
        if child is not None:
            code = child.wait()
            if code:
                raise RuntimeError(f"Resident selector exited with code {code}")
        else:
            pid = data.get("pid")
            if type(pid) is not int or pid <= 0:
                raise RuntimeError("Resident health lacks a valid process identity")
            endpoint=os.getenv('APERTURE_MODEL_URL','http://127.0.0.1:8765').rstrip('/')+'/health'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while process_alive(pid):
                with opener.open(endpoint,timeout=2) as response:
                    current=json.load(response)
                if current.get('pid')!=pid or not current.get('ready') or current.get('startup_token')!=data.get('startup_token'):
                    raise RuntimeError('Resident selector identity changed')
                time.sleep(0.5)
    except KeyboardInterrupt:
        return
    finally:
        if child is not None:
            stop_started_process(child)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--query", "--question", "-q")
    parser.add_argument("--query-id", "--id", "--task-id", dest="qid")
    parser.add_argument("--url", "--start-url", "--website", "--site", default="")
    parser.add_argument("--output-dir")
    parser.add_argument("--input", "--input-file", "--tasks", help="UTF-8 JSON tasks or JSONL")
    parser.add_argument("--profile", choices=["minimal", "compat"], default=os.getenv("APERTURE_PROFILE", "minimal"))
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--index", nargs="?", const="")
    args = parser.parse_args(argv)
    if args.serve:
        return serve_resident()
    if args.warmup or args.index is not None:
        print(json.dumps(warmup(), ensure_ascii=True))
        return
    tasks = []
    if args.input:
        raw = Path(args.input).read_text(encoding="utf-8-sig")
        data = [json.loads(line) for line in raw.splitlines() if line.strip()] if args.input.lower().endswith(".jsonl") else json.loads(raw)
        tasks = data if isinstance(data, list) else data.get("tasks", data.get("queries", [data]))
    else:
        tasks = [{"id": args.qid or os.getenv("QUERY_ID"),
                  "query": args.query or args.question or os.getenv("QUERY", ""),
                  "url": args.url or os.getenv("START_URL", "")}]
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            task = {"query": "", "id": f"invalid_{i+1}"}
        query = task.get("query") or task.get("question") or task.get('task') or ""
        qid = task.get("query_id", task.get("id", f"query_{i+1}" if args.input else None))
        result = run_query(query, task.get("url") or task.get("start_url", ""), qid,
                           args.output_dir, args.profile, args.diagnostics)
        # ASCII JSON escapes keep stdout valid even under a legacy Windows code page.
        # The UTF-8 result file still preserves the original Unicode spelling.
        print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
