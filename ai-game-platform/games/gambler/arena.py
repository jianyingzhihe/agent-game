"""One-command arena launcher: HTTP server + browser + game.

Usage:
    cd ai-game-platform
    python -m games.gambler.arena              # default: 20 rounds
    python -m games.gambler.arena 30           # 30 rounds
    python -m games.gambler.arena 20 42        # 20 rounds, random seed 42
    python -m games.gambler.arena --resume     # resume from last saved state
"""

import os
import sys
import socket
import threading
import webbrowser
import mimetypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)

from core.game_launcher import build_models_and_names, check_models, print_players
from core.logger import GameLogger
from core.utils import Colors

from .engine import GamblerEngine
from .player import GamblerPlayer

DEFAULT_PORT = 9999
BUF_SIZE = 65536


def _find_port(preferred: int = DEFAULT_PORT) -> int:
    for offset in range(20):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return preferred


def _start_http_server(port: int, root: str):
    """Minimal single-threaded HTTP server — works reliably on Windows."""

    def serve():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))
        sock.listen(8)
        sock.settimeout(1.0)  # so we can check shutdown

        while getattr(serve, 'running', True):
            try:
                conn, _ = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                data = conn.recv(BUF_SIZE)
                if not data:
                    conn.close()
                    continue

                request = data.decode('utf-8', errors='replace')
                line = request.split('\r\n')[0]
                parts = line.split()
                if len(parts) < 2:
                    conn.close()
                    continue

                path = parts[1].split('?')[0]  # strip query string
                if path == '/':
                    path = '/index.html'

                file_path = os.path.join(root, path.lstrip('/'))
                file_path = os.path.normpath(file_path)

                # Security: prevent directory traversal
                if not file_path.startswith(os.path.normpath(root)):
                    conn.sendall(b'HTTP/1.1 403 Forbidden\r\n\r\n')
                    conn.close()
                    continue

                if os.path.isfile(file_path):
                    mime, _ = mimetypes.guess_type(file_path)
                    content_type = mime or 'application/octet-stream'
                    with open(file_path, 'rb') as f:
                        body = f.read()
                    resp = (
                        f'HTTP/1.1 200 OK\r\n'
                        f'Content-Type: {content_type}\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'Cache-Control: no-cache\r\n'
                        f'\r\n'
                    ).encode('utf-8') + body
                else:
                    body = b'{"error":"not found"}'
                    resp = (
                        f'HTTP/1.1 404 Not Found\r\n'
                        f'Content-Type: application/json\r\n'
                        f'Content-Length: {len(body)}\r\n'
                        f'\r\n'
                    ).encode('utf-8') + body

                conn.sendall(resp)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        try:
            sock.close()
        except Exception:
            pass

    serve.running = True
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return serve


def _stop_http_server(server):
    server.running = False


def run():
    max_rounds = 20
    seed = None
    resume_mode = False

    args = [a for a in sys.argv[1:] if not a.startswith("--resume")]
    if "--resume" in sys.argv:
        resume_mode = True
    if len(args) > 0:
        try:
            max_rounds = int(args[0])
        except ValueError:
            pass
    if len(args) > 1:
        try:
            seed = int(args[1])
        except ValueError:
            pass

    port = _find_port(DEFAULT_PORT)
    root_dir = str(PROJECT_ROOT)
    server = _start_http_server(port, root_dir)
    viewer_url = f'http://127.0.0.1:{port}/games/gambler/viewer.html'

    print(Colors.bold('\n  ===== Gambler Arena ====='))
    print(Colors.color(f'  Viewer: {viewer_url}', Colors.CYAN))
    webbrowser.open(viewer_url)

    state_file = HERE / 'ui_state.json'

    # ---- Resume mode: load saved state ----
    if resume_mode and state_file.exists():
        import json as _json
        saved = _json.loads(state_file.read_text(encoding='utf-8'))
        saved_round = saved.get("current_round", 0)
        if saved_round <= 0 or saved.get("finished"):
            print(Colors.color('  No saved game to resume (already finished or not started).', Colors.YELLOW))
            resume_mode = False

    if resume_mode:
        import json as _json
        saved = _json.loads(state_file.read_text(encoding='utf-8'))
        saved_round = saved["current_round"]
        saved_names = [p["name"] for p in saved["players"]]

        print(Colors.color(f'\n  Resuming from round {saved_round}...', Colors.CYAN))

        # Build models and match to saved players by name
        try:
            entries = check_models(build_models_and_names())
        except SystemExit:
            entries = []

        entry_by_name = {n: (n, m, p) for n, m, p in entries}
        players = []
        for sname in saved_names:
            if sname in entry_by_name:
                n, m, p = entry_by_name[sname]
                players.append(GamblerPlayer(name=n, model=m, persona=p))
                print(f'  {sname}: loaded (was ${saved["players"][saved_names.index(sname)]["current_assets"]:,.2f})')
            else:
                print(Colors.color(f'  {sname}: model not available, skipping', Colors.YELLOW))

        if len(players) < 1:
            print(Colors.color('  No players could be restored.', Colors.RED))
            _stop_http_server(server)
            return

        log_dir = os.getenv('LOG_DIR', str(PROJECT_ROOT / 'logs'))
        logger = GameLogger('gambler', base_dir=log_dir)
        engine = GamblerEngine.resume(players, saved, logger=logger)

        print(Colors.dim(f'  Continuing from round {engine.round}, {saved["game_config"]["max_rounds"] - engine.round} rounds remaining'))
        engine.run(verbose=True, resumed=True)
    else:
        # ---- New game ----
        try:
            entries = check_models(build_models_and_names())
        except SystemExit:
            entries = []

        if len(entries) < 1:
            print(Colors.color('  No API keys configured! Create .env with at least one provider key.', Colors.RED))
            print(Colors.color(f'  Viewer still available at {viewer_url}', Colors.CYAN))
            print(Colors.dim('  Press Ctrl+C to stop.'))
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                print('\n  Server stopped.')
            finally:
                _stop_http_server(server)
            return

        players = [
            GamblerPlayer(name=n, model=m, persona=p)
            for n, m, p in entries[:8]
        ]
        print_players(players)

        config = {
            'state_file': str(state_file),
            'max_rounds': max_rounds,
        }
        if seed is not None:
            config['random_seed'] = seed

        if seed is not None:
            print(Colors.dim(f'  Random seed: {seed} (deterministic)'))
        print(Colors.dim(f'  {max_rounds} rounds, same roll per round for all gamblers'))

        log_dir = os.getenv('LOG_DIR', str(PROJECT_ROOT / 'logs'))
        logger = GameLogger('gambler', base_dir=log_dir)
        engine = GamblerEngine(players, config=config, logger=logger)
        engine.run(verbose=True)

    print(f'\n  {Colors.color("Game finished!", Colors.GREEN)}')
    print(f'  {Colors.color(f"Viewer: {viewer_url}", Colors.CYAN)}')
    print(Colors.dim('  Press Ctrl+C to stop the server.'))

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print('\n  Server stopped.')
    finally:
        _stop_http_server(server)


if __name__ == '__main__':
    run()
