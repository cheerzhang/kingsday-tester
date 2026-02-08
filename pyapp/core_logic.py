import json, os

# ======================
# Paths
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLES_DIR = os.path.join(ROOT, "data", "roles")
RUNTIME_DIR = os.path.join(ROOT, "data", "runtime")
WINRATE_PATH = os.path.join(RUNTIME_DIR, "winrate.json")

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default

def role_path(role_id: str) -> str:
    return os.path.join(ROLES_DIR, f"{role_id}.json")  # if you store by id filename
    # If your filenames are different (e.g. role_finn.json),
    # you should instead search ROLES_DIR to find the file by role_obj["id"].

def load_role_by_id(role_id: str) -> dict:
    # robust: scan files and match "id"
    if not os.path.isdir(ROLES_DIR):
        return {}
    for fn in os.listdir(ROLES_DIR):
        if not fn.endswith(".json"):
            continue
        obj = _load_json(os.path.join(ROLES_DIR, fn), {})
        if obj.get("id") == role_id:
            return obj
    return {}

def gamestate_path(role_id: str) -> str:
    return os.path.join(RUNTIME_DIR, f"{role_id}_gamestate.json")

def load_gamestate(role_id: str) -> dict:
    return _load_json(gamestate_path(role_id), {"role_id": role_id, "status": {}})

# ======================
# Draw card eligibility
# ======================
def can_pay_cost(status: dict, resource: str, delta: int) -> bool:
    """
    True if status[resource] + delta >= 0
    delta is usually negative (e.g. -1).
    """
    if not isinstance(status, dict):
        return False
    try:
        cur = int(status.get(resource, 0))
        d = int(delta)
    except Exception:
        return False
    return (cur + d) >= 0

def _normalize_cost_option(opt: dict) -> dict | None:
    if not isinstance(opt, dict):
        return None
    # multi-cost option
    if isinstance(opt.get("costs"), list):
        costs = []
        for c in opt.get("costs"):
            if not isinstance(c, dict):
                continue
            res = c.get("resource")
            delta = c.get("delta")
            if not res:
                continue
            costs.append({"resource": str(res), "delta": int(delta)})
        if not costs:
            return None
        return {"costs": costs}
    # single-cost option
    res = opt.get("resource")
    delta = opt.get("delta")
    if not res:
        return None
    return {"costs": [{"resource": str(res), "delta": int(delta)}]}

def check_draw_card_eligibility(role_obj: dict, gamestate_obj: dict) -> tuple[bool, list[dict]]:
    """
    Returns:
      (can_draw, payable_options)

    payable_options is a list of options that can be paid now, each like:
      {"resource": "...", "delta": -1}
    """
    dc = role_obj.get("draw_card_cost")
    if not isinstance(dc, dict):
        return (False, [])

    options = dc.get("options")
    if not isinstance(options, list) or not options:
        return (False, [])

    status = gamestate_obj.get("status")
    if not isinstance(status, dict):
        status = {}

    payable = []
    for opt in options:
        norm = _normalize_cost_option(opt)
        if not norm:
            continue
        costs = norm.get("costs", [])
        if all(can_pay_cost(status, c["resource"], c["delta"]) for c in costs):
            payable.append(norm)

    return (len(payable) > 0, payable)


def save_gamestate(role_id: str, gamestate_obj: dict):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    with open(gamestate_path(role_id), "w", encoding="utf-8") as f:
        json.dump(gamestate_obj, f, ensure_ascii=False, indent=2)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def apply_cost_option(role_id: str, option: dict) -> dict:
    """
    option: {"resource": "...", "delta": -1}
    Applies to runtime gamestate.status and saves.
    Returns updated gamestate dict.
    """
    gs = load_gamestate(role_id)
    st = gs.get("status")
    if not isinstance(st, dict):
        st = {}
        gs["status"] = st

    costs = option.get("costs")
    if isinstance(costs, list) and costs:
        for c in costs:
            if not isinstance(c, dict):
                continue
            res = str(c.get("resource", "")).strip()
            delta = int(c.get("delta", 0))
            if not res:
                continue
            try:
                cur = int(st.get(res, 0))
            except Exception:
                cur = 0
            st[res] = cur + delta
            if st[res] < 0:
                st[res] = 0
    else:
        res = str(option.get("resource", "")).strip()
        delta = int(option.get("delta", 0))
        try:
            cur = int(st.get(res, 0))
        except Exception:
            cur = 0
        st[res] = cur + delta
        if st[res] < 0:
            st[res] = 0  # 防负数（你说先不做严格校验，这里简单保护）

    save_gamestate(role_id, gs)
    return gs

def get_draw_cost_config(role_obj: dict) -> tuple[str, list[dict]]:
    dc = role_obj.get("draw_card_cost")
    if not isinstance(dc, dict):
        return ("THEN", [])
    logic = str(dc.get("logic", "THEN")).upper()
    if logic not in ("THEN", "OR"):
        logic = "THEN"
    opts = dc.get("options", [])
    if not isinstance(opts, list):
        opts = []
    # normalize
    out = []
    for o in opts:
        norm = _normalize_cost_option(o)
        if norm:
            out.append(norm)
    return (logic, out)

# ==========================================================
# 胜率 Helper
# ==========================================================


def update_winrate(players: list[str], winners: list[str]):
    key = "|".join(sorted(players))

    data = _load_json(WINRATE_PATH, {"total_games": 0, "by_player_set": {}})
    data["total_games"] += 1

    rec = data["by_player_set"].setdefault(key, {
        "games": 0,
        "wins": {}
    })

    rec["games"] += 1
    for w in winners:
        rec["wins"][w] = rec["wins"].get(w, 0) + 1

    save_json(WINRATE_PATH, data)
