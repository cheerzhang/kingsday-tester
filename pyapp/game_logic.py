import json
import os

# ======================
# Paths
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLES_DIR = os.path.join(ROOT, "data", "roles")
RUNTIME_DIR = os.path.join(ROOT, "data", "runtime")
CURRENT_GAME_PATH = os.path.join(RUNTIME_DIR, "current_game.json")

REQUIRED_ROLE_IDS = {"role_finn", "role_tourist"}
VENDOR_ROLE_ID = "role_vendor"

# ======================
# IO helpers
# ======================
def _ensure_dirs():
    os.makedirs(ROLES_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default

def _save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def role_gamestate_path(role_id: str) -> str:
    _ensure_dirs()
    return os.path.join(RUNTIME_DIR, f"{role_id}_gamestate.json")

# ======================
# Roles reading (minimal)
# ======================
def list_role_files():
    _ensure_dirs()
    return sorted(f for f in os.listdir(ROLES_DIR) if f.endswith(".json"))

def load_role_by_file(filename: str) -> dict:
    return _load_json(os.path.join(ROLES_DIR, filename), default={})

def load_all_roles_min():
    """
    Returns list of:
      { "id", "name", "file", "init_number" }
    """
    roles = []
    for fn in list_role_files():
        obj = load_role_by_file(fn)
        rid = str(obj.get("id", "")).strip()
        name = str(obj.get("name", "")).strip()
        init_number = obj.get("init_number")

        if not rid or not name or not isinstance(init_number, dict):
            continue

        roles.append({
            "id": rid,
            "name": name,
            "file": fn,
            "init_number": init_number
        })
    return roles

# ======================
# Runtime init
# ======================
def init_game_runtime(selected_role_ids: list[str]) -> list[str]:
    _ensure_dirs()

    # de-dup & enforce required roles
    chosen = list(dict.fromkeys(selected_role_ids))
    for req in REQUIRED_ROLE_IDS:
        if req not in chosen:
            chosen.insert(0, req)

    # load role configs
    role_map = {r["id"]: r for r in load_all_roles_min()}

    # create gamestate for each role
    for rid in chosen:
        role = role_map.get(rid)
        if not role:
            continue

        status = {}
        for k, cfg in role["init_number"].items():
            if isinstance(cfg, dict):
                try:
                    status[k] = int(cfg.get("number", 0))
                except Exception:
                    status[k] = 0

        # universal progress
        status.setdefault("progress", 0)

        gs = {
            "role_id": rid,
            "status": status
        }

        # vendor extra runtime fields (only init, no logic here)
        if rid == VENDOR_ROLE_ID:
            gs["counters"] = {
                "trades_done": 0,
                "trade_partners": []
            }
            gs["progress_detail"] = {
                "target_trades": 0,
                "target_unique_partners": 0,
                "trades_done": 0,
                "unique_partners": 0
            }
            tsi = role.get("trade_state_init", {})
            if isinstance(tsi, dict):
                gs["trade_state"] = json.loads(json.dumps(tsi))  # deep copy
            else:
                gs["trade_state"] = {"price_mod": 1, "price_override": {"product": 1, "orange_product": 2}}

        _save_json(role_gamestate_path(rid), gs)

    # write current_game.json
    cur = {
        "players": chosen,
        "game_over": False,
        "game_over_reason": "",
        "events_drawn": []
    }
    _save_json(CURRENT_GAME_PATH, cur)

    return chosen

# ======================
# Runtime read helpers
# ======================
def load_current_game():
    _ensure_dirs()
    return _load_json(
        CURRENT_GAME_PATH,
        {"players": [], "game_over": False, "game_over_reason": ""}
    )

def load_player_gamestate(role_id: str) -> dict:
    return _load_json(
        role_gamestate_path(role_id),
        {"role_id": role_id, "status": {}}
    )

# ======================
# Runtime reset
# ======================
def reset_runtime():
    """
    Delete runtime temp files.
    """
    _ensure_dirs()

    for fn in os.listdir(RUNTIME_DIR):
        if fn.endswith("_gamestate.json") or fn == "current_game.json":
            try:
                os.remove(os.path.join(RUNTIME_DIR, fn))
            except Exception:
                pass

# ======================
# Game loop driver (VERY THIN)
# ======================
def run_game_loop(player_turn_fn):
    """
    Drive the game loop.

    player_turn_fn signature:
        player_turn_fn(role_id: str) -> None

    Flow:
      while not game_over:
        for each player:
          if game_over: break
          call player_turn_fn(role_id)
    """
    cur = load_current_game()
    players = cur.get("players", [])

    if not players:
        return

    idx = 0
    while True:
        cur = load_current_game()
        if cur.get("game_over"):
            break

        rid = players[idx % len(players)]
        player_turn_fn(rid)

        idx += 1