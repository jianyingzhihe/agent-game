"""Batch evaluation utilities for Werewolf logs.

Phase 6 focuses on turning completed matches into measurable signals.
This script scans `logs/werewolf/` and prints aggregate metrics for recent sessions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


LOG_ROOT = Path("logs/werewolf")


def load_summary_files(root: Path = LOG_ROOT) -> List[Dict]:
    summaries: List[Dict] = []
    if not root.exists():
        return summaries

    for path in sorted(root.glob("*/summary.json")):
        try:
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue

    return summaries


def safe_avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_sessions(summaries: List[Dict]) -> Dict[str, float]:
    total_sessions = len(summaries)
    werewolf_wins = 0
    villager_wins = 0
    total_rounds: List[float] = []
    seer_alive_rounds: List[float] = []
    hunter_shot_count = 0
    last_words_count = 0
    runoff_count = 0
    antidote_uses = 0
    poison_uses = 0

    for summary in summaries:
        winner = summary.get("winner")
        if winner == "werewolf":
            werewolf_wins += 1
        elif winner == "villager":
            villager_wins += 1

        total_rounds.append(float(summary.get("total_rounds", 0)))

        players = summary.get("players", [])
        for player in players:
            role = str(player.get("role", "")).lower()
            private_state = player.get("private_state", {})

            if "seer" in role:
                checks = private_state.get("seer_checks", [])
                seer_alive_rounds.append(float(len(checks)))

            if "hunter" in role:
                shot_history = private_state.get("hunter", {}).get("shot_history", [])
                if shot_history:
                    hunter_shot_count += 1

            if "witch" in role:
                witch_state = private_state.get("witch", {})
                antidote_uses += len(witch_state.get("antidote_target_history", []))
                poison_uses += len(witch_state.get("poison_target_history", []))

        extra = summary.get("extra", {})
        if extra.get("vote_history"):
            runoff_count += sum(1 for item in extra["vote_history"] if "runoff" in str(item).lower())
        if summary.get("timeline"):
            last_words_count += sum(
                1 for item in summary["timeline"] if "Last words from" in str(item)
            )

    return {
        "total_sessions": total_sessions,
        "werewolf_win_rate": werewolf_wins / total_sessions if total_sessions else 0.0,
        "villager_win_rate": villager_wins / total_sessions if total_sessions else 0.0,
        "avg_rounds": safe_avg(total_rounds),
        "avg_seer_checks": safe_avg(seer_alive_rounds),
        "hunter_shot_rate": hunter_shot_count / total_sessions if total_sessions else 0.0,
        "avg_antidote_uses": antidote_uses / total_sessions if total_sessions else 0.0,
        "avg_poison_uses": poison_uses / total_sessions if total_sessions else 0.0,
        "avg_runoff_count": runoff_count / total_sessions if total_sessions else 0.0,
        "avg_last_words_count": last_words_count / total_sessions if total_sessions else 0.0,
    }


def main() -> None:
    summaries = load_summary_files()
    metrics = evaluate_sessions(summaries)

    print("Werewolf Evaluation")
    print(f"Sessions: {metrics['total_sessions']}")
    print(f"Werewolf win rate: {metrics['werewolf_win_rate']:.2%}")
    print(f"Villager win rate: {metrics['villager_win_rate']:.2%}")
    print(f"Average rounds: {metrics['avg_rounds']:.2f}")
    print(f"Average seer checks: {metrics['avg_seer_checks']:.2f}")
    print(f"Hunter shot rate: {metrics['hunter_shot_rate']:.2%}")
    print(f"Average antidote uses: {metrics['avg_antidote_uses']:.2f}")
    print(f"Average poison uses: {metrics['avg_poison_uses']:.2f}")
    print(f"Average runoff count: {metrics['avg_runoff_count']:.2f}")
    print(f"Average last words count: {metrics['avg_last_words_count']:.2f}")


if __name__ == "__main__":
    main()
