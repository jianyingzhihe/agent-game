"""One-command arena launcher: HTTP server + browser + game.

Usage:
    cd ai-game-platform
    python -m games.gambler.arena                    # default config
    python -m games.gambler.arena my_config.yaml     # custom config
    python -m games.gambler.arena my_config.yaml 30  # override max_rounds
    python -m games.gambler.arena my_config.yaml 30 42  # + seed
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

import yaml

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


def _load_config(path: Path) -> dict:
    """Load game config from a YAML file. Returns empty dict if not found."""
    if not path.exists():
        print(Colors.color(f'  Config file not found: {path}, using defaults.', Colors.YELLOW))
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
        return cfg if isinstance(cfg, dict) else {}


def run():
    # Parse CLI: [config_file] [max_rounds] [seed]
    args = [a for a in sys.argv[1:] if not a.startswith('--resume')]
    resume = '--resume' in sys.argv

    config_path = HERE / 'config.yaml'
    cli_max_rounds = None
    cli_seed = None
    arg_offset = 0

    # First arg: config file (if ends with .yaml/.yml) or max_rounds (if int)
    if len(args) > 0:
        if args[0].endswith('.yaml') or args[0].endswith('.yml'):
            config_path = Path(args[0])
            if not config_path.is_absolute():
                config_path = Path.cwd() / config_path
            arg_offset = 1
        else:
            try:
                cli_max_rounds = int(args[0])
                arg_offset = 1
            except ValueError:
                pass

    # Remaining args
    remaining = args[arg_offset:]
    if len(remaining) > 0:
        try:
            cli_max_rounds = int(remaining[0])
        except ValueError:
            pass
    if len(remaining) > 1:
        try:
            cli_seed = int(remaining[1])
        except ValueError:
            pass

    # Load config from YAML
    config = _load_config(config_path)
    print(Colors.dim(f'  Config: {config_path}'))

    # CLI overrides
    if cli_max_rounds is not None:
        config['max_rounds'] = cli_max_rounds
    if cli_seed is not None:
        config['random_seed'] = cli_seed

    config['state_file'] = str(HERE / 'ui_state.json')

    max_rounds = int(config.get('max_rounds', 30))

    port = _find_port(DEFAULT_PORT)
    root_dir = str(PROJECT_ROOT)
    server = _start_http_server(port, root_dir)
    viewer_url = f'http://127.0.0.1:{port}/games/gambler/viewer.html'

    print(Colors.bold('\n  ===== Gambler Arena ====='))
    print(Colors.color(f'  Viewer: {viewer_url}', Colors.CYAN))
    webbrowser.open(viewer_url)

    # Build players
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

    seed = config.get('random_seed')
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
