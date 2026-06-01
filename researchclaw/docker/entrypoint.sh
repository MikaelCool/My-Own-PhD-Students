#!/bin/bash
# ResearchClaw experiment entrypoint — unified three-phase execution.
#
# Phase 0: pip install from requirements.txt (if present)
# Phase 1: Run setup.py for dataset downloads / preparation (if present)
# Phase 2: Run the main experiment script
#
# Environment variables:
#   RC_SETUP_ONLY_NETWORK=1  — disable network after Phase 1 (iptables/route)
#   RC_ENTRY_POINT           — override entry point (default: first CLI arg or main.py)
set -e

WORKSPACE="/workspace"
ENTRY_POINT="${1:-main.py}"
SETUP_CACHE="$WORKSPACE/.cache/setup"
RUNTIME_CACHE="$WORKSPACE/.cache/runtime"
mkdir -p "$SETUP_CACHE" "$RUNTIME_CACHE"

SHARED_HF_CACHE="$WORKSPACE/.cache/huggingface"
SHARED_DATASETS_CACHE="$WORKSPACE/data/hf"
if [ -d "$SHARED_HF_CACHE" ]; then
    mkdir -p "$SHARED_HF_CACHE/assets" "$SHARED_HF_CACHE/transformers" "$SHARED_HF_CACHE/hub"
fi
if [ -d "$SHARED_DATASETS_CACHE" ]; then
    mkdir -p "$SHARED_DATASETS_CACHE"
fi

_configure_hf_cache_env() {
    local phase_cache="$1"
    export XDG_CACHE_HOME="$phase_cache"
    if [ -d "$SHARED_HF_CACHE" ]; then
        export HF_HOME="$SHARED_HF_CACHE"
        export HF_ASSETS_CACHE="$SHARED_HF_CACHE/assets"
        export TRANSFORMERS_CACHE="$SHARED_HF_CACHE/transformers"
        export HF_HUB_CACHE="$SHARED_HF_CACHE/hub"
    else
        export HF_HOME="$phase_cache/huggingface"
        export HF_ASSETS_CACHE="$phase_cache/huggingface/assets"
        export TRANSFORMERS_CACHE="$phase_cache/huggingface/transformers"
        export HF_HUB_CACHE="$phase_cache/huggingface/hub"
    fi
    if [ -d "$SHARED_DATASETS_CACHE" ]; then
        export HF_DATASETS_CACHE="$SHARED_DATASETS_CACHE"
    fi
}

export XDG_CACHE_HOME="$SETUP_CACHE"
_configure_hf_cache_env "$SETUP_CACHE"

# ----------------------------------------------------------------
# Phase 0: Install additional pip packages
# ----------------------------------------------------------------
if [ -f "$WORKSPACE/requirements.txt" ]; then
    echo "[RC] Phase 0: Installing packages from requirements.txt..."
    pip install --no-cache-dir --break-system-packages \
        -r "$WORKSPACE/requirements.txt" 2>&1 | tail -20
    echo "[RC] Phase 0: Package installation complete."
fi

# ----------------------------------------------------------------
# Phase 1: Run setup script (dataset download / preparation)
# ----------------------------------------------------------------
if [ -f "$WORKSPACE/setup.py" ]; then
    echo "[RC] Phase 1: Running setup.py (dataset download/preparation)..."
    python3 -u "$WORKSPACE/setup.py"
    python3 - <<'PY'
import json, os, time
workspace = "/workspace"
payload = {
    "schema_version": 1,
    "status": "ready",
    "generated_epoch": int(time.time()),
    "setup_cache": os.environ.get("XDG_CACHE_HOME", ""),
    "entry_point": os.environ.get("RC_ENTRY_POINT", "") or "main.py",
}
with open(os.path.join(workspace, "DATA_READY.json"), "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2)
PY
    echo "[RC] Phase 1: Setup complete."
fi

# ----------------------------------------------------------------
# Network cutoff (if setup_only policy)
# ----------------------------------------------------------------
if [ "${RC_SETUP_ONLY_NETWORK:-0}" = "1" ]; then
    echo "[RC] Disabling network for experiment phase..."
    # Try iptables first (requires NET_ADMIN capability)
    if iptables -A OUTPUT -j DROP 2>/dev/null; then
        echo "[RC] Network disabled via iptables."
    elif ip route del default 2>/dev/null; then
        echo "[RC] Network disabled via route removal."
    else
        echo "[RC] Warning: Could not disable network (no NET_ADMIN cap or ip route). Continuing with network."
    fi
fi

# ----------------------------------------------------------------
# Phase 2: Run experiment
# ----------------------------------------------------------------
_configure_hf_cache_env "$RUNTIME_CACHE"
export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
echo "[RC] Phase 2: Running experiment ($ENTRY_POINT)..."
exec python3 -u "$WORKSPACE/$ENTRY_POINT"
