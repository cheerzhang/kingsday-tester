import json
import os

# ======================
# Paths
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNTIME_DIR = os.path.join(ROOT, "data", "runtime")
CURRENT_GAME_PATH = os.path.join(RUNTIME_DIR, "current_game.json")

def _ensure_runtime_dir():
    os.makedirs(RUNTIME_DIR, exist_ok=True)

def gamestate_path(role_id: str) -> str:
    _ensure_runtime_dir()
    return os.path.join(RUNTIME_DIR, f"{role_id}_gamestate.json")

# ======================
# IO
# ======================
def load_gamestate(role_id: str) -> dict:
    path = gamestate_path(role_id)
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj
    except FileNotFoundError:
        pass
    except Exception:
        pass
    # if missing/invalid: treat as empty state
    return {"role_id": role_id, "counters": {}}

def get_counter(gs: dict, key: str) -> int:
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        return 0
    try:
        return int(counters.get(key, 0))
    except Exception:
        return 0

def load_current_game() -> dict:
    _ensure_runtime_dir()
    try:
        with open(CURRENT_GAME_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {"players": []}
    except Exception:
        return {"players": []}

# ======================
# Victory condition functions
# ======================
def wear_n_orange_items(role_id: str, params: dict) -> bool:
    n = int(params.get("n", 0)) if isinstance(params, dict) else 0
    gs = load_gamestate(role_id)
    worn = get_counter(gs, "orange_worn")
    return worn >= n

def take_n_photo(role_id: str, params: dict) -> bool:
    n = int(params.get("n", 0)) if isinstance(params, dict) else 0
    gs = load_gamestate(role_id)
    photo = get_counter(gs, "photo")
    return photo >= n

def vendor_trade_dynamic(role_id: str, params: dict) -> bool:
    """
    Win if:
      trades_done >= N
      AND unique_trade_partners >= N-1
    where N = len(current_game.players) - 1
    """
    cur = load_current_game()
    players = cur.get("players", [])
    if not isinstance(players, list):
        players = []

    # 摊主不在本局玩家里：不需要检测，也不更新任何东西
    if role_id not in players:
        return False

    N = max(0, len(players) - 1)
    target_trades = N
    target_unique = max(0, N - 1)

    gs = load_gamestate(role_id)
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters

    trades_done = int(counters.get("trades_done", 0) or 0)

    partners = counters.get("trade_partners", [])
    if not isinstance(partners, list):
        partners = []
    unique_count = len({p for p in partners if isinstance(p, str) and p and p != role_id})

    # 记录进度（只加字段，不删字段）
    gs["progress_detail"] = {
        "target_trades": target_trades,
        "target_unique_partners": target_unique,
        "trades_done": trades_done,
        "unique_partners": unique_count
    }
    # 写回（方便你 UI/调试看进度）
    try:
        with open(gamestate_path(role_id), "w", encoding="utf-8") as f:
            json.dump(gs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return (trades_done >= target_trades) and (unique_count >= target_unique)

# ======================
# Registry / dispatcher
# ======================
VICTORY_REGISTRY = {
    "wear_n_orange_items": wear_n_orange_items,
    "take_n_photo": take_n_photo,
    "vendor_trade_dynamic": vendor_trade_dynamic,
}
