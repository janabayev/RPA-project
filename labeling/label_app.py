"""Phase 2 - labeling app: label the collected job postings in the browser with one click.

Start (from the project folder):
    python labeling/label_app.py

The app opens http://127.0.0.1:8765 in the browser. Each click (or key press) on
"Relevant" / "Not relevant" / "Unsure" is saved immediately to data/labels.csv.

Design decisions (see README, Phase 2):
- Labels are stored in a separate file (data/labels.csv), not in data/jobs_raw.csv.
  The robot appends to jobs_raw.csv while it runs; writing labels into the same file at the
  same time could overwrite freshly scraped rows. With two files, labeling can start while
  the robot is still collecting.
- jobs_raw.csv is re-read whenever it changes, so new postings appear without a restart.
- Postings are shown in a fixed pseudo-random order (sorted by a hash of the job ID), so the
  search queries are mixed and the order stays the same after a restart.
- Only the Python standard library is used.

Export labeled data as one file (raw columns + label + note):
    python labeling/label_app.py --export      ->  data/jobs_labeled.csv
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_DIR, "labeling")
JOBS_CSV = os.path.join(PROJECT_DIR, "data", "jobs_raw.csv")
LABELS_CSV = os.path.join(PROJECT_DIR, "data", "labels.csv")
EXPORT_CSV = os.path.join(PROJECT_DIR, "data", "jobs_labeled.csv")
CRITERIA_MD = os.path.join(APP_DIR, "criteria.md")

LABEL_FIELDS = ["job_id", "label", "note", "labeled_at"]
VALID_LABELS = {"1", "0", "?"}  # "?" = unsure, excluded from training
UI_FIELDS = ["job_id", "url", "title", "company", "location", "date_posted",
             "employment_type", "search_query", "description"]


def order_key(job_id):
    """Stable pseudo-random position of a job in the labeling queue."""
    return hashlib.sha1(job_id.encode("utf-8")).hexdigest()


class JobStore:
    """Reads jobs_raw.csv (cached by modification time) and keeps labels.csv in sync."""

    def __init__(self, jobs_csv, labels_csv):
        self.jobs_csv = jobs_csv
        self.labels_csv = labels_csv
        self.lock = threading.Lock()
        self._jobs, self._jobs_mtime = [], None
        self.labels = self._read_labels()

    # ---- jobs ---------------------------------------------------------------
    def jobs(self):
        if not os.path.exists(self.jobs_csv):
            return []
        mtime = os.path.getmtime(self.jobs_csv)
        if mtime != self._jobs_mtime:
            self._jobs = self._read_jobs()
            self._jobs_mtime = mtime
        return self._jobs

    def _read_jobs(self):
        with open(self.jobs_csv, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        jobs, seen = [], set()
        for row in rows:
            # The robot may be writing the last row right now: a half-written row has
            # missing columns (None). Skip it; it is picked up on the next read.
            if None in row.values() or not row.get("job_id") or row["job_id"] in seen:
                continue
            seen.add(row["job_id"])
            jobs.append({k: row.get(k, "") for k in UI_FIELDS})
        jobs.sort(key=lambda j: order_key(j["job_id"]))
        return jobs

    # ---- labels -------------------------------------------------------------
    def _read_labels(self):
        if not os.path.exists(self.labels_csv):
            return {}
        with open(self.labels_csv, newline="", encoding="utf-8-sig") as f:
            return {r["job_id"]: r for r in csv.DictReader(f) if r.get("job_id")}

    def _write_labels(self):
        # Write to a temp file first, then replace: a crash never leaves a half-written file.
        folder = os.path.dirname(self.labels_csv)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            for row in sorted(self.labels.values(), key=lambda r: r["labeled_at"]):
                writer.writerow({k: row.get(k, "") for k in LABEL_FIELDS})
        os.replace(tmp, self.labels_csv)

    def set_label(self, job_id, label, note=""):
        """label in {"1","0","?"} stores a label; "" removes it (undo)."""
        with self.lock:
            if label == "":
                self.labels.pop(job_id, None)
            else:
                self.labels[job_id] = {
                    "job_id": job_id, "label": label, "note": note.strip(),
                    "labeled_at": datetime.now().isoformat(timespec="seconds"),
                }
            self._write_labels()

    def export(self, path):
        with open(self.jobs_csv, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = [c for c in reader.fieldnames if c != "label"] + ["label", "note"]
            rows = [r for r in reader if None not in r.values()]
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL, extrasaction="ignore")
            writer.writeheader()
            for r in rows:
                lab = self.labels.get(r["job_id"], {})
                r["label"], r["note"] = lab.get("label", ""), lab.get("note", "")
                n += bool(r["label"])
                writer.writerow(r)
        return len(rows), n


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, body, ctype="application/json; charset=utf-8", status=200):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(APP_DIR, "index.html"), "rb") as f:
                    self._send(f.read(), "text/html; charset=utf-8")
            elif path == "/api/jobs":
                with store.lock:
                    payload = {"jobs": store.jobs(), "labels": store.labels}
                self._send(json.dumps(payload, ensure_ascii=False))
            elif path == "/api/criteria":
                text = ""
                if os.path.exists(CRITERIA_MD):
                    with open(CRITERIA_MD, encoding="utf-8") as f:
                        text = f.read()
                self._send(json.dumps({"text": text}, ensure_ascii=False))
            else:
                self._send(json.dumps({"error": "not found"}), status=404)

        def do_POST(self):
            if self.path != "/api/label":
                return self._send(json.dumps({"error": "not found"}), status=404)
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                job_id, label = str(body["job_id"]), str(body.get("label", ""))
                if label and label not in VALID_LABELS:
                    raise ValueError(f"invalid label {label!r}")
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                return self._send(json.dumps({"error": str(e)}), status=400)
            store.set_label(job_id, label, str(body.get("note", "")))
            self._send(json.dumps({"ok": True, "labels": store.labels}, ensure_ascii=False))

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    parser.add_argument("--export", action="store_true", help=f"write {os.path.relpath(EXPORT_CSV, PROJECT_DIR)} and exit")
    args = parser.parse_args()

    store = JobStore(JOBS_CSV, LABELS_CSV)

    if args.export:
        total, labeled = store.export(EXPORT_CSV)
        print(f"Exported {total} jobs ({labeled} labeled) to {EXPORT_CSV}")
        return

    if not os.path.exists(JOBS_CSV):
        sys.exit(f"{JOBS_CSV} not found - run the robot first.")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Labeling app: {url}  ({len(store.jobs())} jobs, {len(store.labels)} labeled)")
    print(f"Labels are saved to {LABELS_CSV} after every click. Stop with Ctrl+C.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
