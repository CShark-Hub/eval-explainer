#!/usr/bin/env python3
"""Serve the eval explainer on localhost.

Usage: serve.py [--results DIR] [--cases DIR] [--port 8077] [--host 127.0.0.1] [--open]
Lists DIR/*.json (default: examples/) and serves index.html. Binds to 127.0.0.1
unless --host says otherwise.

Case tags come from DIR/tags.json ({"case-name": ["tag", ...]}) and, with --cases,
from the `tags:` line of each <case>/prompt.md of a `claude plugin eval` suite.
"""
import argparse
import json
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
RESULTS = HERE / "examples"
CASES = None


def result_files():
    return sorted((p for p in RESULTS.glob("*.json") if p.name != "tags.json"), reverse=True)


def case_tags():
    tags = {}
    tags_file = RESULTS / "tags.json"
    if tags_file.is_file():
        tags.update(json.loads(tags_file.read_text()))
    if CASES:
        for p in sorted(CASES.glob("*/prompt.md")):
            for line in p.read_text().splitlines():
                if line.startswith("tags:"):
                    tags[p.parent.name] = json.loads(line[5:])
    return tags


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/results":
            self.send_json([{"name": p.name, "size": p.stat().st_size} for p in result_files()])
        elif path.startswith("/api/results/"):
            # Only names from the listing: no path traversal.
            files = {p.name: p for p in result_files()}
            p = files.get(path.rsplit("/", 1)[1])
            if p is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(json.loads(p.read_text()))
        elif path == "/api/tags":
            self.send_json(case_tags())
        else:
            self.send_json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass


def main():
    global RESULTS, CASES
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--results", type=Path, default=RESULTS, help="directory of eval JSON files (default: examples/)")
    ap.add_argument("--cases", type=Path, help="eval cases directory, for tags (e.g. evals/cases)")
    ap.add_argument("--port", type=int, default=8077)
    # Docker needs 0.0.0.0 inside the container; compose publishes it on the host's 127.0.0.1 only.
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    RESULTS, CASES = args.results.resolve(), args.cases.resolve() if args.cases else None
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"eval explainer: {url}  ({len(result_files())} result file(s) in {RESULTS})  Ctrl+C to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
