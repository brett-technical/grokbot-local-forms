#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from pathlib import Path
from urllib import error, request
import json
import os
import re

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
FORMS_DIR = Path(os.environ.get("FORMS_DIR") or (ROOT / "submissions"))
WEBHOOK_CONFIG = REPO_ROOT / "webhook.local.json"
HOST = os.environ.get("FORM_HOST") or "127.0.0.1"
PORT = int(os.environ.get("FORM_PORT") or "8765")


def safe_stem(value):
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "form")).strip("-")
    return text or "form"


def notify_requesting_bot(record):
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

    def do_GET(self):
        if self.path.split("?", 1)[0] in ("/", "/index.html"):
            path = ROOT / "index.html"
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/submit":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        answer = str(payload.get("answer") or "").strip()
        if not answer:
            self.send_error(400, "Answer is required")
            return

        now = datetime.now().astimezone()
        created = now.strftime("%Y-%m-%d")
        submitted = now.isoformat(timespec="seconds")
        stamp = now.strftime("%Y-%m-%d-%H%M%S")
        form_id = safe_stem(payload.get("form") or "example-form")
        stem = stamp + "-" + form_id
        FORMS_DIR.mkdir(parents=True, exist_ok=True)

        question = str(payload.get("question") or "Untitled question")
        markdown_path = FORMS_DIR / (stem + ".md")
        json_path = FORMS_DIR / (stem + ".json")
        target_bot = str(payload.get("target_bot") or "").strip()
        title = str(payload.get("title") or "Form response")

        record = {
            "form": form_id,
            "is_test": bool(payload.get("is_test")),
            "title": title,
            "submitted": submitted,
            "question": question,
            "answer": answer,
            "target_bot": target_bot,
            "form_path": str(ROOT),
            "markdown_path": str(markdown_path),
            "json_path": str(json_path),
        }

        markdown = "\n".join(
            [
                "---",
                "title: " + title,
                "created: " + created,
                "submitted: " + submitted,
                "form: " + form_id,
                "status: " + ("test" if record["is_test"] else "submitted"),
                "target_bot: " + target_bot,
                "form_path: " + ROOT.as_posix(),
                "---",
                "",
                "# " + title,
                "",
                "## " + question,
                "",
                answer,
                "",
            ]
        )

        markdown_path.write_text(markdown, encoding="utf-8")
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


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("Form at http://%s:%s/" % (HOST, PORT))
    print("Saving submissions to %s" % FORMS_DIR)
    print("Webhook config at %s" % WEBHOOK_CONFIG)
    server.serve_forever()
