"""Serve the ontology viewer, its Review page, and their endpoints.

    uv run python -m wander.cli viewer      (http://localhost:8765, review at /review)

GET  /                 the viewer: the ontology drawn live, and the Add knowledge panel
GET  /review           the Review page, where a developer applies or rejects proposals
GET  /ontology.json    the ontology (with pending proposals), read live from ontology.yaml
GET  /proposals.json   pending proposals, each checked and with what it would load
POST /propose          stage one change (anyone): validated, not applied
POST /apply            apply chosen proposals (a developer): live ontology + one graph reload
POST /reject           reject one proposal, with a reason

The server listens on localhost only, and there is no sign-in: anyone who can open the page
can propose, and anyone who can open /review can apply. That's fine for a local demo; an
organisation-wide setup would put sign-in in front of /review (see the README).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from wander import proposals, tools
from wander.ontology import Ontology, OntologyError

HERE = Path(__file__).resolve().parent
PAGES = {"/": "index.html", "/index.html": "index.html", "/review": "review.html"}
MAX_BODY = 20_000


def make_handler(ctx: tools.Context):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/ontology.json":
                try:
                    self._json(200, Ontology.load().to_dict())
                except (OntologyError, OSError) as e:
                    self._json(200, {"error": str(e)})
            elif path == "/proposals.json":
                self._json(200, proposals.pending())
            elif path in PAGES:
                self._send(200, "text/html; charset=utf-8", (HERE / PAGES[path]).read_bytes())
            else:
                self._send(404, "text/plain", b"Not found")

        def do_POST(self):
            actions = {
                "/propose": lambda body: proposals.propose(body),
                "/apply": lambda body: proposals.apply(ctx, list(body.get("ids") or []),
                                                       body.get("reviewed_by", "")),
                "/reject": lambda body: proposals.reject(str(body.get("id", "")), body.get("reviewed_by", ""),
                                                         body.get("reason", "")),
            }
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                return self._json(413, {"error": "That request is empty or too large."})
            raw = self.rfile.read(length)  # read it even if we refuse, so the client gets our answer
            if self.path not in actions:
                return self._json(404, {"error": "Not found"})
            # Only the viewer's own pages may change anything: refuse other origins, and anything
            # that isn't JSON (a plain form post from another site can't send JSON).
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host', '')}":
                return self._json(403, {"error": "Changes can only be made from the viewer itself."})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json(415, {"error": "Send the change as JSON."})
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("Send a JSON object.")
                result = actions[self.path](body)
            except (OntologyError, ValueError) as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:  # e.g. Neo4j isn't running while applying
                return self._json(503, {"error": f"The change was saved, but the graph couldn't be "
                                                 f"reloaded: {e}. Is Neo4j running?"})
            self._json(200, result)

        def _json(self, status: int, payload: dict):
            self._send(status, "application/json", json.dumps(payload, ensure_ascii=False).encode())

        def _send(self, status: int, content_type: str, body: bytes):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):  # keep the terminal quiet
            pass

    return Handler


def serve(port: int = 8765, ctx: tools.Context | None = None) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx or tools.Context()))
    print(f"Ontology viewer on http://localhost:{port}, review at http://localhost:{port}/review "
          "(reads ontology.yaml live; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
