#!/usr/bin/env python3
"""Local dev server for the AI Game Platform viewer.

Usage:
    python serve.py              # Start at http://localhost:3251
    python serve.py --port 8080  # Custom port

Features:
- Serves static files from the project root
- GET /api/logs scans logs/ and returns session metadata
- Auto-opens the browser on start
"""

import json
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent


def detect_game_type(summary: dict, game_type_override: str | None = None) -> str:
    players = summary.get("players", [])
    roles_text = " ".join(p.get("role", "") for p in players).lower()
    if any(k in roles_text for k in ("werewolf", "seer", "witch", "hunter")):
        return "werewolf"
    if any(k in roles_text for k in ("merlin", "assassin", "morgana", "servant", "mordred", "percival")):
        return "avalon"
    if any(k in roles_text for k in ("landlord", "farmer")):
        return "doudizhu"
    if any(k in roles_text for k in ("swap", "unlimited_sha", "blood_draw", "wound_draw", "wound_steal", "empty_draw", "empty_immune")):
        return "sanguosha"
    if game_type_override in ("sgs",):
        return "sanguosha"
    return game_type_override or summary.get("game_type", "unknown")


def scan_logs() -> list[dict]:
    """Scan logs/ for game sessions, newest first."""
    logs_dir = ROOT / "logs"
    if not logs_dir.is_dir():
        return []

    sessions: list[dict] = []

    def add_session(session_dir: Path, game_type_override: str | None = None) -> dict | None:
        jsonl = session_dir / "game.jsonl"
        summary_file = session_dir / "summary.json"
        if not jsonl.is_file():
            return None

        session = {
            "id": session_dir.name,
            "jsonl_path": str(jsonl.relative_to(ROOT)).replace("\\", "/"),
        }

        if summary_file.is_file():
            try:
                summary = json.loads(summary_file.read_text(encoding="utf-8"))
                session["summary"] = summary
                session["gameType"] = detect_game_type(summary, game_type_override)
                session["winner"] = summary.get("winner", "?")
                session["playerCount"] = len(summary.get("players", []))
                session["totalRounds"] = summary.get("total_rounds", 0)
            except Exception:
                session["gameType"] = game_type_override or "unknown"
        else:
            session["gameType"] = game_type_override or "unknown"

        return session

    for game_dir in sorted(logs_dir.iterdir()):
        if not game_dir.is_dir():
            continue
        if (game_dir / "game.jsonl").is_file():
            session = add_session(game_dir)
            if session:
                sessions.append(session)
            continue

        game_type = game_dir.name
        for session_dir in sorted(game_dir.iterdir(), reverse=True):
            if not session_dir.is_dir():
                continue
            session = add_session(session_dir, game_type_override=game_type)
            if session:
                sessions.append(session)

    sessions.sort(key=lambda s: s.get("id", ""), reverse=True)
    return sessions


class ViewerHandler(SimpleHTTPRequestHandler):
    """Serves static files from ROOT and exposes /api/logs."""

    def __init__(self, *args, **kwargs):
        self.directory = str(ROOT)
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/api/logs", "/api/logs/"):
            self._handle_logs_api()
            return
        if path == "/":
            path = "/viewer.html"
        self.path = path
        super().do_GET()

    def _handle_logs_api(self):
        sessions = scan_logs()
        body = json.dumps(sessions, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        if "/api/logs" in str(args):
            print(f"  API: returned {len(scan_logs())} sessions")
        else:
            print(f"  {args[0]}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI Game Platform local server")
    parser.add_argument("--port", type=int, default=3251, help="Port (default: 3251)")
    args = parser.parse_args()

    print("AI Game Platform Viewer")
    print(f"  Root: {ROOT}")
    print(f"  URL:  http://localhost:{args.port}")
    print(f"  API:  http://localhost:{args.port}/api/logs")
    print("  Press Ctrl+C to stop.\n")

    sessions = scan_logs()
    print(f"Found {len(sessions)} game sessions in logs/")

    webbrowser.open(f"http://localhost:{args.port}")

    server = HTTPServer(("127.0.0.1", args.port), ViewerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
