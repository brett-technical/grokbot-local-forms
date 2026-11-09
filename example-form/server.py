#!/usr/bin/env python3
"""Generic local form server. Renders from form.json; never edit per form."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path
from urllib import error, request
import json
import os
import re
import threading
import time

ROOT = Path(__file__).resolve().parent
FORMS_DIR = Path(os.environ.get("FORMS_DIR") or (ROOT / "submissions"))
WEBHOOK_CONFIG = ROOT.parent / "webhook.local.json"
HOST = os.environ.get("FORM_HOST") or "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("FORM_PORT") or "8765")
IDLE_SECONDS = int(os.environ.get("FORM_IDLE_SECONDS") or "3600")
PORT_ATTEMPTS = 50
DISABLE_WEBHOOK = os.environ.get("FORM_DISABLE_WEBHOOK", "").strip().lower() in ("1", "true", "yes")

_activity_lock = threading.Lock()
_last_activity = time.monotonic()


def safe_stem(value):
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "form")).strip("-")
    return text or "form"


def touch_activity():
    global _last_activity
    with _activity_lock:
        _last_activity = time.monotonic()


def load_form_meta():
    path = ROOT / "form.json"
    meta = {"id": ROOT.name, "title": ROOT.name, "target_bot": "Web Apps", "requested_by": None}
    if not path.exists():
        return meta
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return meta
    if isinstance(data, dict):
        if data.get("id"):
            meta["id"] = safe_stem(data["id"])
        if data.get("title"):
            meta["title"] = str(data["title"]).strip() or meta["title"]
        if data.get("target_bot"):
            meta["target_bot"] = str(data["target_bot"]).strip() or meta["target_bot"]
        if data.get("requested_by"):
            meta["requested_by"] = str(data["requested_by"]).strip() or None
    return meta


def collect_questions(payload):
    items = payload.get("questions")
    cleaned = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            raw_selected = item.get("selected") or []
            if not isinstance(raw_selected, list):
                raw_selected = [raw_selected]
            selected = [str(value).strip() for value in raw_selected if str(value).strip()]
            other = str(item.get("other") or item.get("answer") or "").strip()
            if question and (selected or other):
                cleaned.append({
                    "id": safe_stem(item.get("id") or question),
                    "question": question,
                    "selected": selected,
                    "other": other,
                })
    if cleaned:
        return cleaned
    question = str(payload.get("question") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if question and answer:
        return [{"id": "answer", "question": question, "selected": [], "other": answer}]
    return []


def format_answer(item):
    parts = []
    if item["selected"]:
        parts.append("Selected: " + "; ".join(item["selected"]))
    if item["other"]:
        parts.append("Your own words: " + item["other"])
    return "\n".join(parts)


def notify_requesting_bot(record):
    if DISABLE_WEBHOOK:
        return {"notified": False, "reason": "webhook_disabled"}
    if not WEBHOOK_CONFIG.exists():
        return {"notified": False, "reason": "missing_webhook_config"}
    try:
        cfg = json.loads(WEBHOOK_CONFIG.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {"notified": False, "reason": "invalid_webhook_config"}

    url = str(cfg.get("url") or "").strip()
    key = str(cfg.get("key") or cfg.get("sender_key") or "").strip()
    if (not url) or url.startswith("PASTE_") or (not key) or key.startswith("PASTE_"):
        return {"notified": False, "reason": "webhook_config_incomplete"}

    body = json.dumps(record).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            code = resp.getcode()
        if code == 200:
            return {"notified": True, "reason": "ok"}
        return {"notified": False, "reason": "webhook_status_%s" % code}
    except error.HTTPError as exc:
        return {"notified": False, "reason": "webhook_status_%s" % exc.code}
    except Exception as exc:
        return {"notified": False, "reason": type(exc).__name__}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _send_bytes(self, data, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            touch_activity()
            data = (ROOT / "index.html").read_bytes()
            self._send_bytes(data, "text/html; charset=utf-8")
            return
        if path == "/form.json":
            touch_activity()
            form_path = ROOT / "form.json"
            if not form_path.exists():
                self.send_error(404, "form.json missing")
                return
            data = form_path.read_bytes()
            self._send_bytes(data, "application/json; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/submit":
            self.send_error(404)
            return
        touch_activity()
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        questions = collect_questions(payload)
        if not questions:
            self.send_error(400, "At least one answer is required")
            return

        meta = load_form_meta()
        now = datetime.now().astimezone()
        created = now.strftime("%Y-%m-%d")
        submitted = now.isoformat(timespec="seconds")
        stamp = now.strftime("%Y-%m-%d-%H%M%S")
        form_id = safe_stem(payload.get("form") or meta["id"])
        stem = stamp + "-" + form_id
        FORMS_DIR.mkdir(parents=True, exist_ok=True)

        markdown_path = FORMS_DIR / (stem + ".md")
        json_path = FORMS_DIR / (stem + ".json")
        target_bot = str(payload.get("target_bot") or meta["target_bot"]).strip() or meta["target_bot"]
        title = str(payload.get("title") or meta["title"])

        record = {
            "form": form_id,
            "is_test": bool(payload.get("is_test")),
            "title": title,
            "submitted": submitted,
            "questions": questions,
            "question": questions[0]["question"],
            "answer": "\n\n".join(
                item["question"] + "\n" + format_answer(item) for item in questions
            ),
            "target_bot": target_bot,
            "form_path": str(ROOT),
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }
        if meta.get("requested_by"):
            record["requested_by"] = meta["requested_by"]

        markdown_lines = [
            "---",
            "title: " + title,
            "created: " + created,
            "submitted: " + submitted,
            "form: " + form_id,
            "status: " + ("test" if record["is_test"] else "submitted"),
            "target_bot: " + target_bot,
        ]
        if meta.get("requested_by"):
            markdown_lines.append("requested_by: " + meta["requested_by"])
        markdown_lines.extend([
            "form_path: " + ROOT.as_posix(),
            "---",
            "",
            "# " + title,
            "",
        ])
        for item in questions:
            markdown_lines.extend(["## " + item["question"], "", format_answer(item), ""])

        markdown_path.write_text("\n".join(markdown_lines), encoding="utf-8")
        json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        notify = notify_requesting_bot(record)
        print("notify: %s" % notify)

        body = json.dumps(
            {
                "ok": True,
                "saved": str(markdown_path),
                "notified": notify["notified"],
                "notify_reason": notify["reason"],
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FormServer(ThreadingHTTPServer):
    allow_reuse_address = False


def bind_server(host, preferred_port):
    last_error = None
    for port in range(preferred_port, preferred_port + PORT_ATTEMPTS):
        try:
            return FormServer((host, port), Handler), port
        except OSError as exc:
            last_error = exc
    raise SystemExit(
        "No free localhost port in %s-%s: %s"
        % (preferred_port, preferred_port + PORT_ATTEMPTS - 1, last_error)
    )


def idle_watch(server, idle_seconds):
    if idle_seconds <= 0:
        return
    while True:
        time.sleep(30)
        with _activity_lock:
            idle_for = time.monotonic() - _last_activity
        if idle_for >= idle_seconds:
            print("Idle for %s seconds; shutting down" % int(idle_for))
            server.shutdown()
            return


if __name__ == "__main__":
    meta = load_form_meta()
    server, port = bind_server(HOST, PREFERRED_PORT)
    print("Form at http://%s:%s/" % (HOST, port), flush=True)
    if port != PREFERRED_PORT:
        print("Port %s was in use; using %s" % (PREFERRED_PORT, port), flush=True)
    print("Form id: %s" % meta["id"], flush=True)
    print("Saving submissions to %s" % FORMS_DIR, flush=True)
    print("Webhook config at %s" % WEBHOOK_CONFIG, flush=True)
    if DISABLE_WEBHOOK:
        print("Webhook: disabled via FORM_DISABLE_WEBHOOK", flush=True)
    if IDLE_SECONDS > 0:
        print("Idle timeout: %s seconds" % IDLE_SECONDS, flush=True)
        watcher = threading.Thread(
            target=idle_watch, args=(server, IDLE_SECONDS), daemon=True
        )
        watcher.start()
    else:
        print("Idle timeout: disabled", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
