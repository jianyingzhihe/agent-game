"""Game logger — per-game organized logs.

Each game creates: logs/{game_type}/{timestamp}/
  game.jsonl   — every prompt, response, action as JSON lines
  summary.json — final result (players, roles, winner, timeline)
  config.json  — game configuration (type, players, models, settings)
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class GameLogger:
    """Records every model interaction and game event to disk."""

    def __init__(self, game_type: str, base_dir: str = "logs"):
        self.game_type = game_type
        self.base_dir = base_dir
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(base_dir, game_type, self.session_id)
        os.makedirs(self.session_dir, exist_ok=True)

        self.jsonl_path = os.path.join(self.session_dir, "game.jsonl")
        self._jsonl_file = open(self.jsonl_path, "w", encoding="utf-8")
        self._event_index = 0
        self._config: Dict[str, Any] = {"game_type": game_type}

    # ---- Public API ----

    def set_config(self, config: Dict[str, Any]) -> None:
        """Set game-specific config (called before game starts)."""
        self._config.update(config)

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self._write({
            "index": self._event_index,
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            **data,
        })

    def log_game_start(self, players: List[Any]) -> None:
        player_info = []
        for p in players:
            info = {
                "name": p.name,
                "model": p.model.model_name,
                "provider": type(p.model).__name__,
            }
            if hasattr(p, 'role') and p.role:
                info["role"] = p.role.name if hasattr(p.role, 'name') else str(p.role)
            if hasattr(p, 'faction'):
                info["faction"] = p.faction
            if hasattr(p, 'team'):
                info["team"] = p.team
            player_info.append(info)
        self.log_event("game_start", {"players": player_info})

    def log_prompt(self, player_name, phase, round_num, system_prompt, user_prompt):
        idx = self._event_index
        self._write({
            "index": idx, "timestamp": datetime.now().isoformat(),
            "type": "prompt", "player": player_name, "phase": phase,
            "round": round_num,
            "system_prompt": system_prompt, "user_prompt": user_prompt,
        })
        return idx

    def log_response(self, player_name, phase, round_num, raw_response, parsed, prompt_index, latency_ms=0, thinking=""):
        record = {
            "index": self._event_index, "timestamp": datetime.now().isoformat(),
            "type": "response", "player": player_name, "phase": phase,
            "round": round_num,
            "raw_response": raw_response,
            "parsed": {k: v for k, v in parsed.items()},
            "prompt_index": prompt_index, "latency_ms": latency_ms,
        }
        if thinking:
            record["thinking"] = thinking
        self._write(record)

    def log_round_start(self, round_num):
        self.log_event("round_start", {"round": round_num})

    def log_round_end(self, round_num, summary):
        self.log_event("round_end", {"round": round_num, **summary})

    def write_summary(self, players, winner, total_rounds, game_log, extra=None):
        summary = {
            "session_id": self.session_id,
            "game_type": self.game_type,
            "winner": winner,
            "total_rounds": total_rounds,
            "total_events": self._event_index,
            "config": self._config,
            "players": [],
            "timeline": game_log,
        }
        if extra:
            summary["extra"] = extra
        for p in players:
            info = {
                "name": p.name,
                "model": p.model.model_name,
                "alive": getattr(p, 'alive', True),
                "persona": getattr(p, 'persona', ''),
            }
            if hasattr(p, 'role') and p.role:
                info["role"] = p.role.name if hasattr(p.role, 'name') else str(p.role)
            if hasattr(p, 'faction'):
                info["faction"] = p.faction
            if hasattr(p, 'chips'):
                info["chips"] = p.chips
            if hasattr(p, 'score'):
                info["score"] = p.score
            if hasattr(p, 'identity') and p.identity:
                info["identity"] = p.identity.value
                info["identity_revealed"] = getattr(p, 'identity_revealed', False)
            summary["players"].append(info)

        # Write summary
        with open(os.path.join(self.session_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Write config
        with open(os.path.join(self.session_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({
                "session_id": self.session_id,
                "game_type": self.game_type,
                "players": summary["players"],
                "config": self._config,
            }, f, ensure_ascii=False, indent=2)

        # Update logs/index.json for auto-discovery by viewer
        self._update_index(summary)

        self._jsonl_file.close()
        return os.path.join(self.session_dir, "summary.json")

    def _update_index(self, summary: Dict[str, Any]) -> None:
        """Append this session to logs/index.json for viewer auto-discovery."""
        index_path = os.path.join(self.base_dir, "index.json")
        sessions = []
        if os.path.exists(index_path):
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
            except (json.JSONDecodeError, IOError):
                sessions = []

        # Build entry for this session
        rel_path = f"{self.game_type}/{self.session_id}/game.jsonl"
        entry = {
            "id": self.session_id,
            "jsonl_path": rel_path,
        }
        # Copy relevant summary fields
        for key in ("winner", "total_rounds", "players", "game_type", "config"):
            if key in summary:
                entry[key] = summary[key]

        # Remove old entry for this session if present, then prepend
        sessions = [s for s in sessions if s.get("id") != self.session_id]
        sessions.insert(0, entry)
        # Keep max 50 entries
        sessions = sessions[:50]

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

    def _write(self, record):
        self._jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl_file.flush()
        self._event_index += 1

    @property
    def log_dir(self):
        return self.session_dir
