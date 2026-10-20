#!/usr/bin/env python3
"""Serve the eval explainer on localhost.

Usage: serve.py [--results DIR ...] [--cases DIR] [--port 8077] [--host 127.0.0.1] [--open]
Scans each DIR recursively (default: examples/) for `claude plugin eval` result
JSON, recognised by content, so a plugin folder, its evals/ or its evals/results/
all work. More folders can be added from the page while it runs. Binds to
127.0.0.1 unless --host says otherwise.

Case tags come from tags.json in a scanned folder ({"case-name": ["tag", ...]}),
from the `tags:` line of any <cases>/<case>/prompt.md found in a scanned folder,
and from --cases.
"""
import argparse
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
INDEX = HERE / "index.html"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", "dist", "build"}
MAX_DEPTH = 8
MAX_JSON_BYTES = 200 * 1024 * 1024

ROOTS = []  # resolved directories, in the order they were added
CASES = None
LOCK = threading.Lock()
_sniffed = {}  # path -> (mtime, size, summary or None)


def walk(root, depth=0):
    """Yield files below root, skipping VCS/dependency folders and very deep trees."""
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return
    for e in entries:
        if e.is_dir(follow_symlinks=False):
            if e.name not in SKIP_DIRS and depth < MAX_DEPTH:
                yield from walk(e.path, depth + 1)
        elif e.is_file():
            yield Path(e.path)


def sniff(path):
    """Summary of an eval result file, or None when the JSON is something else. Cached by mtime."""
    try:
        st = path.stat()
    except OSError:
        return None
    hit = _sniffed.get(path)
    if hit and hit[:2] == (st.st_mtime, st.st_size):
        return hit[2]
    summary = None
    if st.st_size <= MAX_JSON_BYTES:
        try:
            d = json.loads(path.read_bytes())
            if isinstance(d, dict) and isinstance(d.get("cases"), list) and isinstance(d.get("suite"), dict):
                s = d["suite"]
                summary = {
                    "startedAt": d.get("startedAt"),
                    "cases": len(d["cases"]),
                    "ablation": s.get("ablation"),
                    "plugins": [p.get("name") for p in s.get("plugins") or [] if isinstance(p, dict)],
                }
        except (OSError, ValueError, UnicodeDecodeError):
            pass
    _sniffed[path] = (st.st_mtime, st.st_size, summary)
    return summary


def tilde(path):
    """Show paths under the home folder as ~/…, for display only."""
    home = Path.home()
    return "~/" + path.relative_to(home).as_posix() if path.is_relative_to(home) else str(path)


def label(root, path):
    """Readable name: the path below the root, e.g. evals/results/20261011-222149/aggregate-result.json."""
    rel = path.relative_to(root).as_posix()
    return f"{root.name}/{rel}"


def result_files():
    """Every result file under every root: [{id, name, root, size, mtime, ...summary}], newest first."""
    out, seen = [], set()
    with LOCK:
        roots = list(ROOTS)
    for i, root in enumerate(roots):
        for p in walk(root):
            if p.suffix != ".json" or p.name == "tags.json" or p in seen:
                continue
            summary = sniff(p)
            if summary is None:
                continue
            seen.add(p)
            st = p.stat()
            out.append({"id": f"{i}:{p.relative_to(root).as_posix()}", "name": label(root, p), "file": p.name,
                        "root": str(root), "rootLabel": tilde(root), "size": st.st_size, "mtime": st.st_mtime, **summary})
    out.sort(key=lambda f: (f["startedAt"] or "", f["mtime"]), reverse=True)
    return out


def resolve_id(fid):
    """Map an id from the listing back to a file. Only listed files resolve: no path traversal."""
    files = {f["id"]: f for f in result_files()}
    f = files.get(fid)
    if f is None:
        return None
    i, rel = fid.split(":", 1)
    return ROOTS[int(i)] / rel


def read_tags(prompt_md, tags):
    for line in prompt_md.read_text(errors="replace").splitlines():
        if line.startswith("tags:"):
            try:
                tags[prompt_md.parent.name] = json.loads(line[5:])
            except ValueError:
                pass


def case_tags():
    tags = {}
    with LOCK:
        roots = list(ROOTS)
    for root in roots:
        for p in walk(root):
            if p.name == "tags.json":
                try:
                    t = json.loads(p.read_text())
                    if isinstance(t, dict):
                        tags.update(t)
                except (OSError, ValueError):
                    pass
            elif p.name == "prompt.md" and p.parent.parent.name == "cases":
                read_tags(p, tags)
    if CASES:
        for p in sorted(CASES.glob("*/prompt.md")):
            read_tags(p, tags)
    return tags


def add_root(path):
    """Add a folder to scan. Returns (root, error)."""
    try:
        root = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        return None, str(e)
    if not root.is_dir():
        return None, f"not a directory: {root}"
    with LOCK:
        if root not in ROOTS:
            ROOTS.append(root)
    return root, None


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        # Rejects DNS-rebinding requests: another site's hostname pointed at 127.0.0.1.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
        self.send_json({"error": "forbidden host"}, 403)
        return False

    def do_GET(self):
        if not self.local_host():
            return
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/results":
            self.send_json(result_files())
        elif url.path == "/api/result":
            p = resolve_id(q.get("id", [""])[0])
            if p is None:
                self.send_json({"error": "not found"}, 404)
            else:
                self.send_json(json.loads(p.read_bytes()))
        elif url.path == "/api/tags":
            self.send_json(case_tags())
        elif url.path == "/api/dirs":
            with LOCK:
                self.send_json([str(r) for r in ROOTS])
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.local_host():
            return
        # application/json forces a CORS preflight, which this server never answers: other sites cannot post here.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.send_json({"error": "expected application/json"}, 415)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad JSON"}, 400)
        if urlsplit(self.path).path != "/api/dirs" or not isinstance(body.get("path"), str):
            return self.send_json({"error": "not found"}, 404)
        root, err = add_root(body["path"])
        if err:
            return self.send_json({"error": err}, 400)
        found = [f for f in result_files() if f["root"] == str(root)]
        self.send_json({"root": str(root), "label": tilde(root), "found": len(found)})

    def log_message(self, fmt, *args):
        pass


def main():
    global CASES
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--results", type=Path, action="append",
                    help="folder to scan for eval JSON, recursively; repeatable (default: examples/)")
    ap.add_argument("--cases", type=Path, help="eval cases directory, for tags (e.g. evals/cases)")
    ap.add_argument("--port", type=int, default=8077)
    # Docker needs 0.0.0.0 inside the container; compose publishes it on the host's 127.0.0.1 only.
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    for d in args.results or [HERE / "examples"]:
        root, err = add_root(d)
        if err:
            ap.error(err)
    CASES = args.cases.resolve() if args.cases else None
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"eval explainer: {url}  ({len(result_files())} result file(s) in {', '.join(map(tilde, ROOTS))})  Ctrl+C to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
