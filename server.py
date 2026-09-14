"""Small loopback-only web interface for the notes index."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from search import SearchIndex, read_passages


def make_handler(index):
    page = Path(__file__).with_name("web").joinpath("index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/":
                self.send(200, page, "text/html; charset=utf-8")
            elif url.path == "/api/search":
                try:
                    query = parse_qs(url.query).get("q", [""])[0]
                    data = {"hits": index.search(query), "passages": len(index.passages)}
                    self.send(200, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")
                except ValueError as error:
                    self.send(400, json.dumps({"error": str(error)}).encode(), "application/json")
            else:
                self.send(404, b"Not found", "text/plain")

        def log_message(self, format, *args):
            # Queries may contain personal text; avoid writing them to access logs.
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, nargs="?", default=Path("examples/notes"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        index = SearchIndex(read_passages(args.folder))
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(index))
    except (OSError, UnicodeError, ValueError, OverflowError) as error:
        parser.error(str(error))
    print("Alem Notes: http://127.0.0.1:{} ({} passages)".format(args.port, len(index.passages)), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
