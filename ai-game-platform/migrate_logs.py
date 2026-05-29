"""Move old flat logs into per-game subdirectories."""

import json, os, shutil

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Known game types by session ID
MAPPING = {
    "werewolf": [
        "20260502_233959", "20260503_113508", "20260503_114304",
        "20260504_113701", "20260504_113709", "20260504_115041",
        "20260504_135935", "20260507_173139",
    ],
    "avalon": [
        "20260503_192650", "20260503_214023",
    ],
    "doudizhu": [
        "20260503_173637", "20260507_173928", "20260507_175149",
        "20260507_175831", "20260507_180908", "20260507_181803",
    ],
}

for game, sessions in MAPPING.items():
    target_dir = os.path.join(LOG_DIR, game)
    os.makedirs(target_dir, exist_ok=True)
    for sid in sessions:
        src = os.path.join(LOG_DIR, sid)
        dst = os.path.join(target_dir, sid)
        if os.path.exists(src):
            shutil.move(src, dst)
            print(f"  {sid} → logs/{game}/")
        else:
            print(f"  {sid} (not found)")

print("\nDone.")
