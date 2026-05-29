#!/usr/bin/env python3
"""Quick model health check — sends 'Hello' to each configured model.

Also supports --all to test every unique model in PLAYER_CONFIG,
including multi-model gateways like DashScope.
"""

import os, sys, time
from dotenv import load_dotenv

load_dotenv()
project_root = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(project_root, ".env"))
sys.path.insert(0, project_root)

from core.models.factory import create_model, PROVIDER_CONFIGS

def env(key, default=""):
    val = os.getenv(key, default)
    return val.strip().strip('"').strip("'") if val else default

def test_one(provider, model_name, base_url=""):
    """Test a single model. Returns (ok, elapsed_ms, response_text)."""
    key = env(f"{provider}_KEY")
    if not key:
        return None

    kwargs = {}
    if model_name: kwargs["model"] = model_name
    if base_url: kwargs["base_url"] = base_url

    try:
        model = create_model(provider, api_key=key, **kwargs)
        t0 = time.time()
        thinking, resp = model.chat([{"role": "user", "content": "Hello"}])
        elapsed = (time.time() - t0) * 1000
        if not resp or "ERROR:" in resp[:30]:
            raise RuntimeError(resp[:100] or "empty response")
        return (True, elapsed, resp.strip()[:80])
    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err: hint = f"bad key — {err[:120]}"
        elif "404" in err or "not found" in err.lower() or "not open" in err.lower(): hint = f"not found — {err[:120]}"
        elif "timeout" in err.lower(): hint = f"timeout — {err[:80]}"
        else: hint = err[:200]
        return (False, 0, hint)

def parse_player_config():
    """Parse PLAYER_CONFIG to get unique (provider, model) pairs."""
    cfg = env("PLAYER_CONFIG", "")
    if not cfg:
        return []
    seen = set()
    result = []
    for part in cfg.split(","):
        part = part.strip()
        if not part: continue
        pieces = part.split(":")
        p = pieces[0].strip().upper()
        if len(pieces) >= 3:
            m, c = pieces[1].strip(), pieces[2].strip()
        elif len(pieces) == 2:
            m, c = "", pieces[1].strip()
        else:
            m, c = "", "1"
        key = (p, m)
        if key not in seen:
            seen.add(key)
            result.append((p, m))
    return result

# ---- Main ----

test_all = "--all" in sys.argv

print(f"\n  Model Health Check\n")

if test_all:
    # Test every unique model from PLAYER_CONFIG
    models_to_test = parse_player_config()
    if not models_to_test:
        print("  No PLAYER_CONFIG found — testing defaults instead.\n")
        models_to_test = [(p.upper(), "") for p in PROVIDER_CONFIGS if env(f"{p}_KEY")]
    print(f"  Testing {len(models_to_test)} model(s) from PLAYER_CONFIG:\n")
else:
    # Test default model for each configured provider
    models_to_test = [(p.upper(), "") for p in list(PROVIDER_CONFIGS.keys()) + ["gemini"] if env(f"{p}_KEY")]
    print(f"  Testing default model for {len(models_to_test)} configured provider(s):\n")

# Test MiniMax first — it's the fragile one
if models_to_test:
    mm = [(p, m) for p, m in models_to_test if "minimax" in p.lower() or "minimax" in m.lower()]
    rest = [(p, m) for p, m in models_to_test if not ("minimax" in p.lower() or "minimax" in m.lower())]
    models_to_test = mm + rest

ok, fail = [], []

for provider, model_name in models_to_test:
    cfg = PROVIDER_CONFIGS.get(provider.lower(), {})
    effective_model = model_name or env(f"{provider}_MODEL") or cfg.get("default_model", "?")
    base_url = env(f"{provider}_BASE_URL") or cfg.get("base_url", "")

    label = f"{provider}/{effective_model}" if model_name else f"{provider} ({effective_model})"
    result = test_one(provider, effective_model, base_url)

    if result is None:
        continue
    is_ok, elapsed, detail = result
    if is_ok:
        ok.append(label)
        print(f"  ✅ {label:50s} {elapsed:6.0f}ms  → \"{detail}\"")
    else:
        fail.append((label, detail))
        print(f"  ❌ {label}")
        print(f"     {detail}")

total = len(ok) + len(fail)
print(f"\n  {'─'*60}")
print(f"  Passed: {len(ok)} / {total}")
if fail:
    print(f"  Failed: {', '.join(p for p,_ in fail)}")
print()
