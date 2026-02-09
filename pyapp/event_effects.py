import json
import os

# ======================
# Paths
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNTIME_DIR = os.path.join(ROOT, "data", "runtime")
GAME_FILE = os.path.join(RUNTIME_DIR, "current_game.json")
GLOBAL_DEFS_PATH = os.path.join(ROOT, "data", "global_defs.json")

def _ensure_runtime():
    os.makedirs(RUNTIME_DIR, exist_ok=True)

def role_gamestate_path(role_id: str) -> str:
    _ensure_runtime()
    return os.path.join(RUNTIME_DIR, f"{role_id}_gamestate.json")

# ======================
# IO helpers
# ======================
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default

def _load_trade_defaults() -> dict:
    obj = load_json(GLOBAL_DEFS_PATH, {})
    td = obj.get("trade_defaults")
    if not isinstance(td, dict):
        return {"price_mod": 1, "price_override": {"product": 1, "orange_product": 2}}
    return td

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_current_game():
    _ensure_runtime()
    return load_json(GAME_FILE, {
        "players": [],
        "game_over": False,
        "game_over_reason": ""
    })

def _ensure_global_trade_state(g: dict) -> dict:
    gts = g.get("global_trade_state")
    if not isinstance(gts, dict):
        gts = {}
        g["global_trade_state"] = gts
    return gts

def save_current_game(obj: dict):
    _ensure_runtime()
    save_json(GAME_FILE, obj)

def set_last_event_context(ctx: dict):
    g = load_current_game()
    if isinstance(ctx, dict):
        g["last_event_context"] = ctx
    else:
        g.pop("last_event_context", None)
    save_current_game(g)

def get_last_event_context() -> dict:
    g = load_current_game()
    lec = g.get("last_event_context")
    return lec if isinstance(lec, dict) else {}

def get_players_from_current_game():
    obj = load_current_game()
    players = obj.get("players", [])
    return players if isinstance(players, list) else []

# ======================
# Normalize helpers
# ======================
def _dict(v):
    return v if isinstance(v, dict) else {}

def _list(v):
    return v if isinstance(v, list) else []

def _norm_params_players(params, players):
    return _dict(params), _list(players)

def _targets_excluding(actor_id: str, players):
    return [rid for rid in _list(players) if rid and rid != actor_id]

# ======================
# Gamestate helpers
# ======================
def load_role_gamestate(role_id: str) -> dict:
    return load_json(
        role_gamestate_path(role_id),
        {"role_id": role_id, "status": {}}
    )

def save_role_gamestate(role_id: str, gs: dict):
    save_json(role_gamestate_path(role_id), gs)

def add_status(role_id: str, key: str, delta: int):
    gs = load_role_gamestate(role_id)
    st = gs.get("status")
    if not isinstance(st, dict):
        st = {}
        gs["status"] = st

    try:
        cur = int(st.get(key, 0))
    except Exception:
        cur = 0

    val = cur + int(delta)
    if val < 0:
        val = 0

    st[key] = val
    save_role_gamestate(role_id, gs)

def _add_counter(role_id: str, key: str, delta: int):
    gs = load_role_gamestate(role_id)
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters
    try:
        cur = int(counters.get(key, 0))
    except Exception:
        cur = 0
    counters[key] = cur + int(delta)
    save_role_gamestate(role_id, gs)

def record_volunteer_help(volunteer_id: str, action_type: str) -> bool:
    gs = load_role_gamestate(volunteer_id)
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters
    types = counters.get("help_types")
    if not isinstance(types, list):
        types = []
    action_type = str(action_type).strip()
    if not action_type:
        return False
    if action_type in types:
        save_role_gamestate(volunteer_id, gs)
        return False
    types.append(action_type)
    counters["help_types"] = types
    # progress +1 for new type
    st = gs.get("status")
    if not isinstance(st, dict):
        st = {}
        gs["status"] = st
    try:
        st["progress"] = int(st.get("progress", 0)) + 1
    except Exception:
        st["progress"] = 1
    save_role_gamestate(volunteer_id, gs)
    return True

# ======================
# Finn wear helpers
# ======================
def _get_status_int(gs: dict, key: str) -> int:
    st = gs.get("status")
    if not isinstance(st, dict):
        return 0
    try:
        return int(st.get(key, 0))
    except Exception:
        return 0

def check_finn_wear_requirements(gs: dict) -> tuple[bool, str]:
    worn = _get_status_int(gs, "orange_wear_product")
    orange_product = _get_status_int(gs, "orange_product")
    curiosity = _get_status_int(gs, "curiosity")
    stamina = _get_status_int(gs, "stamina")

    need_curiosity = 2 + worn
    if curiosity < need_curiosity:
        return (False, "need_curiosity")
    if orange_product < 1:
        return (False, "need_orange_product")
    if stamina < 1:
        return (False, "need_stamina")
    return (True, "")

def apply_finn_wear_costs_and_progress(actor_id: str) -> tuple[bool, str]:
    gs = load_role_gamestate(actor_id)
    ok, reason = check_finn_wear_requirements(gs)
    if not ok:
        return (False, reason)
    add_status(actor_id, "stamina", -1)
    add_status(actor_id, "orange_product", -1)
    add_status(actor_id, "progress", 1)
    _add_counter(actor_id, "orange_worn", 1)
    return (True, "")

def apply_finn_wear_no_cost(*, actor_id: str) -> None:
    add_status(actor_id, "orange_wear_product", 1)
    add_status(actor_id, "progress", 1)
    _add_counter(actor_id, "orange_worn", 1)

def apply_photo_progress_only(*, actor_id: str, target_id: str) -> None:
    # progress +1 for actor (tourist)
    add_status(actor_id, "progress", 1)
    # optional counters: photo +1, record target
    gs = load_role_gamestate(actor_id)
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters
    try:
        cur = int(counters.get("photo", 0))
    except Exception:
        cur = 0
    counters["photo"] = cur + 1
    targets = counters.get("photo_targets")
    if not isinstance(targets, list):
        targets = []
    if target_id and target_id not in targets:
        targets.append(target_id)
    counters["photo_targets"] = targets
    save_role_gamestate(actor_id, gs)

# ======================
# Global effect functions
# ======================
def all_role_stat_plus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    All players: status[stat] += amount
    """
    stat = str(params.get("stat", "")).strip()
    amount = int(params.get("amount", 1))

    if not stat or amount == 0:
        return

    for rid in players:
        add_status(rid, stat, amount)

def current_player_stat_plus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    Current player: status[stat] += amount
    """
    if not current_player_id:
        return

    stat = str(params.get("stat", "")).strip()
    amount = int(params.get("amount", 1))

    if not stat or amount == 0:
        return

    add_status(current_player_id, stat, amount)

def current_player_stat_plus_and_minus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    current player: status[stat_plus] += amount_plus; status[stat_minus] += amount_minus
    """
    if not current_player_id:
        return
    stat_plus = str(params.get("stat_plus", "")).strip()
    stat_minus = str(params.get("stat_minus", "")).strip()
    try:
        amount_plus = int(params.get("amount_plus", 0))
    except Exception:
        amount_plus = 0
    try:
        amount_minus = int(params.get("amount_minus", 0))
    except Exception:
        amount_minus = 0
    if stat_plus:
        add_status(current_player_id, stat_plus, amount_plus)
    if stat_minus:
        add_status(current_player_id, stat_minus, amount_minus)

def current_player_money_minus_stamina_plus_skip_finn(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    current player: money -1, stamina +1
    Finn draws: no effect
    """
    if not current_player_id:
        return
    if current_player_id == "role_finn":
        return
    add_status(current_player_id, "money", -1)
    add_status(current_player_id, "stamina", 1)

def current_player_curiosity_and_stamina_plus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    current player: curiosity +1, stamina +1
    """
    if not current_player_id:
        return
    add_status(current_player_id, "curiosity", 1)
    add_status(current_player_id, "stamina", 1)

def current_and_lowest_stamina_plus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    - all lowest-stamina players: stamina +1 (ties included, before change)
    - current player: stamina +1
    """
    if not isinstance(players, list) or not current_player_id:
        return

    # find lowest stamina BEFORE change
    min_sta = None
    for rid in players:
        if not rid:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            sta = int(st.get("stamina", 0))
        except Exception:
            sta = 0
        if min_sta is None or sta < min_sta:
            min_sta = sta
    if min_sta is None:
        return

    lowest_ids = []
    for rid in players:
        if not rid:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            sta = int(st.get("stamina", 0))
        except Exception:
            sta = 0
        if sta == min_sta:
            lowest_ids.append(rid)

    set_last_event_context({"lowest_stamina_targets": lowest_ids})

    for rid in lowest_ids:
        add_status(rid, "stamina", 1)

    add_status(current_player_id, "stamina", 1)
def game_end_immediately(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    End game immediately
    """
    g = load_current_game()
    g["game_over"] = True

    reason = "event: game_end_immediately"
    if current_player_id:
        reason += f" (by {current_player_id})"

    g["game_over_reason"] = reason
    save_current_game(g)

def current_and_lowest_curiosity_plus(*, params: dict, players: list[str], current_player_id=None):
    """
    Effect:
    - Find all players with lowest curiosity (ties included) -> +1
    - Then current player +1
    """
    if not isinstance(players, list) or not players:
        return

    # find minimum curiosity among players
    min_cur = None
    for rid in players:
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if min_cur is None or cur < min_cur:
            min_cur = cur

    if min_cur is None:
        return

    # all lowest curiosity players +1
    lowest_ids = []
    for rid in players:
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if cur == min_cur:
            lowest_ids.append(rid)
            add_status(rid, "curiosity", 1)

    # record lowest list before any changes for role effects
    set_last_event_context({"lowest_curiosity_targets": lowest_ids})

    # current player +1
    if current_player_id:
        add_status(current_player_id, "curiosity", 1)

# ======================
# Dispatcher
# ======================
EFFECT_REGISTRY = {
    "all_role_stat_plus": all_role_stat_plus,
    "current_player_stat_plus": current_player_stat_plus,
    "current_player_stat_plus_and_minus": current_player_stat_plus_and_minus,
    "current_player_money_minus_stamina_plus_skip_finn": current_player_money_minus_stamina_plus_skip_finn,
    "current_player_curiosity_and_stamina_plus": current_player_curiosity_and_stamina_plus,
    "current_and_lowest_stamina_plus": current_and_lowest_stamina_plus,
    "game_end_immediately": game_end_immediately,
    "current_and_lowest_curiosity_plus": current_and_lowest_curiosity_plus,
}

def run_global_effect(
    effect_id: str,
    params: dict | None = None,
    players: list[str] | None = None,
    current_player_id: str | None = None,
):
    """
    Execute global effect by id.

    This function:
    - finds effect function
    - executes it
    - does NOT log
    - does NOT return status
    """
    params = params if isinstance(params, dict) else {}
    players = players if isinstance(players, list) else get_players_from_current_game()

    fn = EFFECT_REGISTRY.get(effect_id)
    if not fn:
        return

    fn(
        params=params,
        players=players,
        current_player_id=current_player_id,
    )



# =========================
# Photo action - state machine
# =========================

def list_photo_targets(actor_id: str, players: list[str]) -> list[str]:
    """
    规则（目标能被拍的条件）：
    - 必须是其他玩家
    - curiosity >= 2
    - 拥有橙色物品（穿/未穿都算）
    - 特例：Finn 必须 orange_worn >= 1 且 curiosity >= 2
    """
    if not isinstance(players, list):
        return []
    targets = []
    actor_gs = load_role_gamestate(actor_id)
    counters = actor_gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
    photo_targets = counters.get("photo_targets")
    if not isinstance(photo_targets, list):
        photo_targets = []

    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        # curiosity gate
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if cur < 2:
            continue
        def _int0(x):
            try:
                return int(x)
            except Exception:
                return 0
        orange_worn = _int0(st.get("orange_wear_product", 0))
        orange_product = _int0(st.get("orange_product", 0))
        if rid == "role_finn":
            if rid in photo_targets:
                continue
            if orange_worn >= 1:
                targets.append(rid)
            continue
        if (orange_worn + orange_product) >= 1:
            targets.append(rid)
    return targets

def list_lowest_curiosity_targets(*, actor_id: str, players: list[str]) -> list[str]:
    if not isinstance(players, list):
        return []

    # prefer last_event_context (before global effect modified curiosity)
    g = load_current_game()
    lec = g.get("last_event_context")
    if isinstance(lec, dict):
        ids = lec.get("lowest_curiosity_targets")
        if isinstance(ids, list) and ids:
            targets = []
            for rid in ids:
                if not rid or rid == actor_id:
                    continue
                gs = load_role_gamestate(rid)
                st = gs.get("status", {})
                if not isinstance(st, dict):
                    st = {}
                try:
                    orange_worn = int(st.get("orange_wear_product", 0))
                except Exception:
                    orange_worn = 0
                if orange_worn >= 1:
                    targets.append(rid)
            return targets

    # fallback: compute by current curiosity
    min_cur = None
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if min_cur is None or cur < min_cur:
            min_cur = cur
    if min_cur is None:
        return []

    targets = []
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        try:
            orange_worn = int(st.get("orange_wear_product", 0))
        except Exception:
            orange_worn = 0
        if cur == min_cur and orange_worn >= 1:
            targets.append(rid)
    return targets

def list_lowest_curiosity_players(*, actor_id: str, players: list[str]) -> list[str]:
    if not isinstance(players, list):
        return []

    g = load_current_game()
    lec = g.get("last_event_context")
    if isinstance(lec, dict):
        ids = lec.get("lowest_curiosity_targets")
        if isinstance(ids, list) and ids:
            return [rid for rid in ids if rid and rid != actor_id]

    min_cur = None
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if min_cur is None or cur < min_cur:
            min_cur = cur
    if min_cur is None:
        return []

    out = []
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0
        if cur == min_cur:
            out.append(rid)
    return out

def list_lowest_stamina_players(*, actor_id: str, players: list[str]) -> list[str]:
    if not isinstance(players, list):
        return []

    g = load_current_game()
    lec = g.get("last_event_context")
    if isinstance(lec, dict):
        ids = lec.get("lowest_stamina_targets")
        if isinstance(ids, list) and ids:
            return [rid for rid in ids if rid and rid != actor_id]

    min_sta = None
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            sta = int(st.get("stamina", 0))
        except Exception:
            sta = 0
        if min_sta is None or sta < min_sta:
            min_sta = sta
    if min_sta is None:
        return []

    out = []
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            sta = int(st.get("stamina", 0))
        except Exception:
            sta = 0
        if sta == min_sta:
            out.append(rid)
    return out

def get_event_selected_target(*, actor_id: str) -> str:
    lec = get_last_event_context()
    target_id = lec.get("selected_target")
    if not target_id or target_id == actor_id:
        return ""
    return str(target_id)

def get_event_watchers(*, actor_id: str | None = None) -> list[str]:
    lec = get_last_event_context()
    ids = lec.get("watchers")
    if not isinstance(ids, list):
        return []
    if actor_id:
        return [rid for rid in ids if rid and rid != actor_id]
    return [rid for rid in ids if rid]

def _get_exchange_item_options(*, role_id: str, allow_wear: bool, only_product: bool = False) -> list[dict]:
    gs = load_role_gamestate(role_id)
    opts = []
    if _get_status_int(gs, "product") > 0:
        opts.append({"kind": "product", "label": "普通物品 x1"})
    if not only_product:
        if _get_status_int(gs, "orange_product") > 0:
            opts.append({"kind": "orange_product", "label": "橙色物品 x1"})
        if allow_wear and _get_status_int(gs, "orange_wear_product") > 0:
            opts.append({"kind": "orange_wear_product", "label": "已佩戴橙色 x1"})
    return opts

def _transfer_exchange_item(*, giver_id: str, receiver_id: str, item_kind: str):
    if item_kind == "orange_wear_product":
        add_status(giver_id, "orange_wear_product", -1)
        # if wearer now has no worn orange, clear buffs
        gs = load_role_gamestate(giver_id)
        if _get_status_int(gs, "orange_wear_product") < 1:
            clear_orange_wear_buffs(role_id=giver_id)
        add_status(receiver_id, "orange_product", 1)
    else:
        add_status(giver_id, item_kind, -1)
        add_status(receiver_id, item_kind, 1)

def swap_items_start(*, actor_id: str, target_id: str, actor_opts: list[dict], target_opts: list[dict], force_agree: bool = False, on_refuse: dict | None = None):
    if not actor_opts or not target_opts:
        return ("done", {"ok": False, "reason": "no_items"}, None)
    pending = {
        "type": "swap_items",
        "stage": "choose_actor_item",
        "actor_id": actor_id,
        "target_id": target_id,
        "actor_options": actor_opts,
        "target_options": target_opts,
        "actor_choice": None,
        "target_choice": None,
        "force_agree": bool(force_agree),
        "on_refuse": on_refuse or {},
    }
    if len(actor_opts) == 1:
        pending["actor_choice"] = actor_opts[0]
        pending["stage"] = "choose_target_item"
    return ("need_exchange_choice", {"options": pending["actor_options"] if pending["actor_choice"] is None else pending["target_options"]}, pending)

def swap_items_choose(*, pending: dict, option_index: int):
    if not isinstance(pending, dict) or pending.get("type") != "swap_items":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") == "choose_actor_item":
        options = pending.get("actor_options", [])
        if option_index < 0 or option_index >= len(options):
            return ("need_exchange_choice", {"options": options, "error": "invalid_choice"}, pending)
        pending["actor_choice"] = options[option_index]
        pending["stage"] = "choose_target_item"
        options = pending.get("target_options", [])
        return ("need_exchange_choice", {"options": options}, pending)
    if pending.get("stage") == "choose_target_item":
        options = pending.get("target_options", [])
        if option_index < 0 or option_index >= len(options):
            return ("need_exchange_choice", {"options": options, "error": "invalid_choice"}, pending)
        pending["target_choice"] = options[option_index]
        pending["stage"] = "need_consent"
        return ("need_exchange_consent", {"target_id": pending.get("target_id")}, pending)
    return ("fail", {"reason": "bad_stage"}, None)

def swap_items_consent(*, pending: dict, agree: bool):
    if not isinstance(pending, dict) or pending.get("type") != "swap_items":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("force_agree"):
        agree = True
    if not agree:
        on_refuse = pending.get("on_refuse") or {}
        if on_refuse.get("type") == "photo":
            actor_id = pending.get("actor_id")
            target_id = pending.get("target_id")
            photo_pending = {
                "type": "try_take_photo",
                "stage": "need_consent",
                "actor_id": actor_id,
                "targets": [target_id],
                "target_id": target_id,
                "params": {},
                "force_agree": True,
            }
            return ("need_consent", {"target_id": target_id}, photo_pending)
        if on_refuse.get("type") == "money":
            actor_id = pending.get("actor_id")
            add_status(actor_id, "money", 1)
            return ("done", {"ok": False, "reason": "refused_money"}, None)
        return ("done", {"ok": False, "reason": "refused"}, None)

    actor_id = pending.get("actor_id", "")
    target_id = pending.get("target_id", "")
    ac = pending.get("actor_choice") or {}
    tc = pending.get("target_choice") or {}
    a_kind = ac.get("kind")
    t_kind = tc.get("kind")
    if not a_kind or not t_kind:
        return ("fail", {"reason": "missing_choice"}, None)
    _transfer_exchange_item(giver_id=actor_id, receiver_id=target_id, item_kind=a_kind)
    _transfer_exchange_item(giver_id=target_id, receiver_id=actor_id, item_kind=t_kind)
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)

def can_take_photo(actor_id: str, actor_gs: dict, target_id: str, target_gs: dict) -> bool:
    """
    门槛：
    - actor money >= 1
    - actor stamina >= 1
    """
    st = actor_gs.get("status", {})
    if not isinstance(st, dict):
        st = {}
    try:
        money = int(st.get("money", 0))
    except Exception:
        money = 0
    try:
        stamina = int(st.get("stamina", 0))
    except Exception:
        stamina = 0
    return (money >= 1) and (stamina >= 1)


def apply_photo_success(
    actor_id: str,
    target_id: str,
    params: dict,
    *,
    load_gs_fn,
    save_gs_fn,
):
    """
    拍照成功效果（落盘到 runtime gamestate）：
    - 被拍的人 money +1
    - 拍照的人 money -1
    - 拍照的人 stamina -1

    额外：记录 counters.photo +1 / photo_targets（可选但推荐）
    """
    # --- load ---
    actor_gs = load_gs_fn(actor_id)
    target_gs = load_gs_fn(target_id)
    def _ensure_status(gs: dict) -> dict:
        if not isinstance(gs, dict):
            gs = {"role_id": ""}
        st = gs.get("status")
        if not isinstance(st, dict):
            st = {}
            gs["status"] = st
        return gs
    actor_gs = _ensure_status(actor_gs)
    target_gs = _ensure_status(target_gs)
    a_st = actor_gs["status"]
    t_st = target_gs["status"]
    def _int0(x):
        try:
            return int(x)
        except Exception:
            return 0
    # --- apply deltas ---
    a_st["money"] = max(0, _int0(a_st.get("money", 0)) - 1)
    a_st["stamina"] = max(0, _int0(a_st.get("stamina", 0)) - 1)
    t_st["money"] = max(0, _int0(t_st.get("money", 0)) + 1)
    # --- optional counters (recommended) ---
    counters = actor_gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        actor_gs["counters"] = counters
    counters["photo"] = _int0(counters.get("photo", 0)) + 1
    targets = counters.get("photo_targets")
    if not isinstance(targets, list):
        targets = []
    if target_id and target_id not in targets:
        targets.append(target_id)
    counters["photo_targets"] = targets
    # ---- tourist progress (photo success) ----
    if actor_id == "role_tourist":
        st = actor_gs.get("status")
        if not isinstance(st, dict):
            st = {}
            actor_gs["status"] = st

        try:
            st["progress"] = int(st.get("progress", 0)) + 1
        except Exception:
            st["progress"] = 1
    # --- save ---
    save_gs_fn(actor_id, actor_gs)
    save_gs_fn(target_id, target_gs)

def apply_photo_success_no_costs(*, actor_id: str, target_id: str):
    """
    Photo success without money/stamina cost (helper via volunteer).
    """
    actor_gs = load_role_gamestate(actor_id)
    target_gs = load_role_gamestate(target_id)
    def _ensure_status(gs: dict) -> dict:
        if not isinstance(gs, dict):
            gs = {"role_id": ""}
        st = gs.get("status")
        if not isinstance(st, dict):
            st = {}
            gs["status"] = st
        return gs
    actor_gs = _ensure_status(actor_gs)
    target_gs = _ensure_status(target_gs)
    # no money/stamina changes
    # counters
    counters = actor_gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        actor_gs["counters"] = counters
    try:
        cur = int(counters.get("photo", 0))
    except Exception:
        cur = 0
    counters["photo"] = cur + 1
    targets = counters.get("photo_targets")
    if not isinstance(targets, list):
        targets = []
    if target_id and target_id not in targets:
        targets.append(target_id)
    counters["photo_targets"] = targets
    # tourist progress
    if actor_id == "role_tourist":
        st = actor_gs.get("status")
        if not isinstance(st, dict):
            st = {}
            actor_gs["status"] = st
        try:
            st["progress"] = int(st.get("progress", 0)) + 1
        except Exception:
            st["progress"] = 1
    save_role_gamestate(actor_id, actor_gs)
    save_role_gamestate(target_id, target_gs)


def try_take_photo_start(*, actor_id: str, players: list[str], params: dict | None = None):
    """
    Step 1: 给出可拍目标 -> need_target
    Returns: (kind, payload, pending)
    """
    params = params if isinstance(params, dict) else {}

    targets = list_photo_targets(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    pending = {
        "type": "try_take_photo",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "target_id": None,
        "params": params,
    }
    payload = {"targets": targets}
    return ("need_target", payload, pending)

def wear_then_photo_start(*, actor_id: str, players: list[str], params: dict | None = None):
    """
    Step 1: choose any target (excluding actor), then wear + photo consent.
    Returns: (kind, payload, pending)
    """
    params = params if isinstance(params, dict) else {}
    if not isinstance(players, list):
        players = []
    targets = [rid for rid in players if rid and rid != actor_id]
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "target_id": None,
        "params": params,
        "pre_action": "wear_target",
    }
    payload = {"targets": targets}
    return ("need_wear_target", payload, pending)

def tourist_photo_lowest_curiosity_start(*, actor_id: str, players: list[str], params: dict | None = None):
    """
    Step 1: choose among lowest-curiosity players (ties included) who are wearing orange.
    Then proceed to consent (forced agree).
    """
    params = params if isinstance(params, dict) else {}
    targets = list_lowest_curiosity_targets(actor_id=actor_id, players=players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "target_id": None,
        "params": params,
        "force_agree": True,
    }
    payload = {"targets": targets}
    return ("need_target", payload, pending)

def vendor_trade_lowest_curiosity_start(*, actor_id: str, players: list[str], params: dict | None = None):
    """
    Step 1: choose item, then choose partner among lowest-curiosity players.
    Partner consent is forced.
    """
    params = params if isinstance(params, dict) else {}
    targets = list_lowest_curiosity_players(actor_id=actor_id, players=players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("fail", {"reason": "no_trade_items"}, None)

    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": targets,
        "force_agree": True,
    }
    return ("need_item", {"items": items}, pending)

def vendor_trade_product_force_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "product") < 1:
        return ("done", {"ok": False, "reason": "no_product"}, None)
    partners = list_trade_partners(
        actor_id=actor_id,
        players=players or [],
        load_gs_fn=load_role_gamestate,
    )
    if not partners:
        return ("done", {"ok": False, "reason": "no_partners"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_partner",
        "actor_id": actor_id,
        "item": {"kind": "product", "amount": 1, "label": "普通物品 x1"},
        "partner_id": None,
        "params": params,
        "force_agree": True,
    }
    return ("need_partner", {"partners": partners, "item": pending.get("item")}, pending)


def try_take_photo_choose_target(*, pending: dict, target_id: str):
    """
    Step 2: 选目标 -> need_consent
    Returns: (kind, payload, pending)
    """
    if not isinstance(pending, dict) or pending.get("type") != "try_take_photo":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "choose_target":
        return ("fail", {"reason": "bad_stage"}, None)

    targets = pending.get("targets", [])
    if not isinstance(targets, list) or target_id not in targets:
        return ("need_target", {"targets": targets, "error": "invalid_target"}, pending)

    # optional pre-action before consent
    if pending.get("pre_action") == "wear_target":
        actor_id = pending.get("actor_id")
        if not actor_id:
            return ("fail", {"reason": "missing_actor"}, None)
        actor_gs = load_role_gamestate(actor_id)
        if _get_status_int(actor_gs, "orange_product") < 1:
            return ("done", {"ok": False, "reason": "need_orange_product"}, None)
        add_status(actor_id, "orange_product", -1)
        if target_id == "role_finn":
            apply_finn_wear_no_cost(actor_id=target_id)
        else:
            add_status(target_id, "orange_wear_product", 1)
        pending.pop("pre_action", None)

    pending["target_id"] = target_id
    pending["stage"] = "need_consent"
    return ("need_consent", {"target_id": target_id}, pending)


def try_take_photo_consent(
    *,
    pending: dict,
    agree: bool,
    load_gs_fn,
    save_gs_fn,
):
    """
    Step 3: 对方同意/拒绝
    - agree False -> done rejected
    - agree True -> gate check -> 成功写入 -> done ok
    Returns: (kind, payload, pending(None))
    """
    if not isinstance(pending, dict) or pending.get("type") != "try_take_photo":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "need_consent":
        return ("fail", {"reason": "bad_stage"}, None)

    actor_id = pending.get("actor_id")
    target_id = pending.get("target_id")
    params = pending.get("params", {})

    if not actor_id or not target_id:
        return ("fail", {"reason": "missing_ids"}, None)

    actor_gs = load_gs_fn(actor_id)
    target_gs = load_gs_fn(target_id)

    # Finn cannot refuse photo
    if target_id == "role_finn":
        agree = True

    # force agree if configured
    if pending.get("force_if_target_wear"):
        try:
            tw = int(target_gs.get("status", {}).get("orange_wear_product", 0))
        except Exception:
            tw = 0
        if tw >= 1:
            agree = True
    if pending.get("force_agree"):
        agree = True

    if not agree:
        try:
            delta = int(params.get("reject_target_curiosity_delta", 0))
        except Exception:
            delta = 0
        if delta != 0:
            add_status(target_id, "curiosity", delta)
        return ("done", {"ok": False, "reason": "rejected"}, None)

    if not can_take_photo(actor_id, actor_gs, target_id, target_gs):
        return ("need_help", {
            "action_type": "photo",
            "actor_id": actor_id,
            "target_id": target_id,
            "params": params,
        }, None)

    apply_photo_success(
        actor_id,
        target_id,
        params,
        load_gs_fn=load_gs_fn,
        save_gs_fn=save_gs_fn,
    )
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)


# =========================
# Trade 
# =========================

def list_trade_items(*, actor_id: str, load_gs_fn) -> list[dict]:
    """
    返回摊主当前可出售的物品列表（按你现在 runtime 字段名）：
    - product > 0  -> 普通物品
    - orange_product > 0 -> 橙色物品（穿不穿无关，这里按 orange_product 作为库存）
    """
    gs = load_gs_fn(actor_id)
    st = gs.get("status", {})
    if not isinstance(st, dict):
        st = {}
    def n(key):
        try:
            return int(st.get(key, 0))
        except Exception:
            return 0
    items = []
    # 普通物品：product
    if n("product") > 0:
        items.append({
            "kind": "product",
            "amount": 1,
            "label": "普通物品 x1"
        })
    # 橙色物品：orange_product
    if n("orange_product") > 0:
        items.append({
            "kind": "orange_product",
            "amount": 1,
            "label": "橙色物品 x1"
        })
    # 食物摊主：food（无限库存）
    if actor_id == "role_food_vendor":
        items.append({
            "kind": "food",
            "amount": 1,
            "label": "食物 x1"
        })
    return items


def try_trade_start(*, actor_id: str, players: list[str], params: dict | None = None):
    """
    Step 1: 检测可交易物品 -> need_item
    Returns: (kind, payload, pending)
    """
    params = params if isinstance(params, dict) else {}

    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("fail", {"reason": "no_trade_items"}, None)

    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
    }
    return ("need_item", {"items": items}, pending)


def try_trade_choose_item(*, pending: dict, item_index: int, players: list[str]):
    """
    Step 2: 选择交易物品 -> need_partner
    """
    if not isinstance(pending, dict) or pending.get("type") != "try_trade":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "choose_item":
        return ("fail", {"reason": "bad_stage"}, None)

    actor_id = pending.get("actor_id")
    if not actor_id:
        return ("fail", {"reason": "missing_actor"}, None)

    # ✅ 重新计算可交易物品（关键修复点）
    items = list_trade_items(
        actor_id=actor_id,
        load_gs_fn=load_role_gamestate,
    )

    if not isinstance(items, list) or not items:
        return ("fail", {"reason": "no_trade_items"}, None)

    # index check
    if item_index < 0 or item_index >= len(items):
        return ("need_item", {"items": items, "error": "invalid_item"}, pending)

    # 记住选择的物品
    chosen_item = items[item_index]
    pending["item"] = chosen_item
    # vendor orange-wear buff: force agree for orange trade
    try:
        item_kind = chosen_item.get("kind")
    except Exception:
        item_kind = None
    if item_kind == "orange_product" and pending.get("actor_id") == "role_vendor":
        seller_gs = load_role_gamestate("role_vendor")
        trade_state = seller_gs.get("trade_state")
        if isinstance(trade_state, dict) and int(trade_state.get("vendor_orange_force_once", 0) or 0) > 0:
            pending["force_agree"] = True
            pending["vendor_orange_force_once"] = True

    # 进入下一阶段
    pending["stage"] = "choose_partner"

    # 计算可交易对象
    partners = list_trade_partners(
        actor_id=actor_id,
        players=players or [],
        load_gs_fn=load_role_gamestate,
    )
    partner_filter = pending.get("partner_filter")
    if isinstance(partner_filter, list):
        partners = [rid for rid in partners if rid in partner_filter]
    if not partners:
        return ("fail", {"reason": "no_partners"}, None)

    return ("need_partner", {"partners": partners, "item": chosen_item}, pending)


def list_trade_partners(*, actor_id: str, players: list[str], load_gs_fn) -> list[str]:
    """
    可交易对象规则：
    - 其他玩家
    - curiosity >= 2（从 runtime gamestate.status 读）
    """
    if not isinstance(players, list):
        return []

    out = []
    for rid in players:
        if not rid or rid == actor_id:
            continue

        gs = load_gs_fn(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}

        try:
            cur = int(st.get("curiosity", 0))
        except Exception:
            cur = 0

        if cur >= 2:
            out.append(rid)

    return out


def try_trade_choose_partner(*, pending: dict, partner_id: str, players: list[str]):
    """
    Step 3: 选择交易对象 -> need_consent
    Returns: (kind, payload, pending)
    """
    if not isinstance(pending, dict) or pending.get("type") != "try_trade":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "choose_partner":
        return ("fail", {"reason": "bad_stage"}, None)

    actor_id = pending.get("actor_id", "")
    if not actor_id:
        return ("fail", {"reason": "missing_actor"}, None)

    # partner 必须是本局玩家之一且不能是自己
    partner_filter = pending.get("partner_filter")
    if (
        not isinstance(players, list)
        or partner_id not in players
        or partner_id == actor_id
        or (isinstance(partner_filter, list) and partner_id not in partner_filter)
    ):
        # 仍然停留在选对象阶段
        partners = list_trade_partners(
            actor_id=actor_id,
            players=players or [],
            load_gs_fn=load_role_gamestate,
        )
        if isinstance(partner_filter, list):
            partners = [rid for rid in partners if rid in partner_filter]
        return ("need_partner", {"partners": partners, "error": "invalid_partner"}, pending)

    # ✅ 记住对象
    pending["partner_id"] = partner_id
    if pending.get("force_if_partner_has_orange"):
        rgs = load_role_gamestate(partner_id)
        if _get_status_int(rgs, "orange_product") >= 1 or _get_status_int(rgs, "orange_wear_product") >= 1:
            pending["force_agree"] = True

    # ✅ 进入下一阶段：同意/拒绝
    pending["stage"] = "need_consent"

    return ("need_consent", {"partner_id": partner_id}, pending)

def can_trade(
    *,
    seller_gs: dict,
    buyer_gs: dict,
    item_key: str,
) -> tuple[bool, str, int]:
    """
    门槛：
    - 卖家好奇 >= 2
    - 买家好奇 >= 2
    - 卖家体力 >= 1
    - 买家金钱 > 商品价格   （注意：你写的是 '>' 不是 '>='，这里按你要求）
    返回：(ok, reason, price)
    """
    seller_st = seller_gs.get("status", {})
    buyer_st = buyer_gs.get("status", {})
    if not isinstance(seller_st, dict):
        seller_st = {}
    if not isinstance(buyer_st, dict):
        buyer_st = {}

    def _i(d, k):
        try:
            return int(d.get(k, 0))
        except Exception:
            return 0

    price = compute_trade_price(seller_gs=seller_gs, item_key=item_key)

    if _i(seller_st, "curiosity") < 2:
        return (False, "seller_curiosity_lt_2", price)
    if _i(buyer_st, "curiosity") < 2:
        return (False, "buyer_curiosity_lt_2", price)
    if _i(seller_st, "stamina") < 1:
        return (False, "seller_stamina_lt_1", price)
    if _i(buyer_st, "money") <= price:  # 你要求 buyer money > price
        return (False, "buyer_money_not_enough", price)

    return (True, "ok", price)

def apply_trade(
    *,
    seller_id: str,
    buyer_id: str,
    item_key: str,   # "product" or "orange_product"
    price: int,
    load_gs_fn,
    save_gs_fn,
):
    """
    执行交易（不做门槛判断，默认门槛已通过）
    Side effects:
      - update seller/buyer runtime gamestate json
    """
    price = int(price)
    if price < 0:
        price = 0

    seller_gs = load_gs_fn(seller_id)
    buyer_gs = load_gs_fn(buyer_id)

    seller_st = seller_gs.get("status")
    if not isinstance(seller_st, dict):
        seller_st = {}
        seller_gs["status"] = seller_st

    buyer_st = buyer_gs.get("status")
    if not isinstance(buyer_st, dict):
        buyer_st = {}
        buyer_gs["status"] = buyer_st

    def _get_int(d, k):
        try:
            return int(d.get(k, 0))
        except Exception:
            return 0

    def _set_nonneg(d, k, v):
        try:
            v = int(v)
        except Exception:
            v = 0
        if v < 0:
            v = 0
        d[k] = v

    # ---- seller changes ----
    seller_item = _get_int(seller_st, item_key)
    seller_money = _get_int(seller_st, "money")
    seller_sta = _get_int(seller_st, "stamina")

    # food vendor has infinite food (no decrement)
    if not (seller_id == "role_food_vendor" and item_key == "food"):
        _set_nonneg(seller_st, item_key, seller_item - 1)
    _set_nonneg(seller_st, "money", seller_money + price)
    _set_nonneg(seller_st, "stamina", seller_sta - 1)

    # ---- buyer changes ----
    buyer_item = _get_int(buyer_st, item_key)
    buyer_money = _get_int(buyer_st, "money")

    _set_nonneg(buyer_st, item_key, buyer_item + 1)
    _set_nonneg(buyer_st, "money", buyer_money - price)

    # ---- vendor progress (trade success) ----
    if seller_id in ("role_vendor", "role_food_vendor"):
        # progress +1
        prog = _get_int(seller_st, "progress")
        _set_nonneg(seller_st, "progress", prog + 1)

        # counters: trades_done +1, unique trade partners
        counters = seller_gs.get("counters")
        if not isinstance(counters, dict):
            counters = {}
            seller_gs["counters"] = counters

        counters["trades_done"] = int(counters.get("trades_done", 0)) + 1

        partners = counters.get("trade_partners")
        if not isinstance(partners, list):
            partners = []
            counters["trade_partners"] = partners
        if buyer_id not in partners:
            partners.append(buyer_id)

        # optional: sync progress_detail if exists
        pd = seller_gs.get("progress_detail")
        if isinstance(pd, dict):
            pd["trades_done"] = counters["trades_done"]
            pd["unique_partners"] = len(partners)

    # ---- persist ----
    save_gs_fn(seller_id, seller_gs)
    save_gs_fn(buyer_id, buyer_gs)

def apply_trade_no_payment(
    *,
    seller_id: str,
    buyer_id: str,
    item_key: str,
):
    """
    Trade success without payment/stamina cost (helper via volunteer).
    """
    seller_gs = load_role_gamestate(seller_id)
    buyer_gs = load_role_gamestate(buyer_id)

    seller_st = seller_gs.get("status")
    if not isinstance(seller_st, dict):
        seller_st = {}
        seller_gs["status"] = seller_st

    buyer_st = buyer_gs.get("status")
    if not isinstance(buyer_st, dict):
        buyer_st = {}
        buyer_gs["status"] = buyer_st

    def _get_int(d, k):
        try:
            return int(d.get(k, 0))
        except Exception:
            return 0

    def _set_nonneg(d, k, v):
        try:
            v = int(v)
        except Exception:
            v = 0
        if v < 0:
            v = 0
        d[k] = v

    # ---- seller changes ----
    seller_item = _get_int(seller_st, item_key)
    if not (seller_id == "role_food_vendor" and item_key == "food"):
        _set_nonneg(seller_st, item_key, seller_item - 1)

    # ---- buyer changes ----
    buyer_item = _get_int(buyer_st, item_key)
    _set_nonneg(buyer_st, item_key, buyer_item + 1)

    # ---- vendor progress (trade success) ----
    if seller_id in ("role_vendor", "role_food_vendor"):
        prog = _get_int(seller_st, "progress")
        _set_nonneg(seller_st, "progress", prog + 1)

        counters = seller_gs.get("counters")
        if not isinstance(counters, dict):
            counters = {}
            seller_gs["counters"] = counters

        counters["trades_done"] = int(counters.get("trades_done", 0)) + 1

        partners = counters.get("trade_partners")
        if not isinstance(partners, list):
            partners = []
            counters["trade_partners"] = partners
        if buyer_id not in partners:
            partners.append(buyer_id)

        pd = seller_gs.get("progress_detail")
        if isinstance(pd, dict):
            pd["trades_done"] = counters["trades_done"]
            pd["unique_partners"] = len(partners)

    save_role_gamestate(seller_id, seller_gs)
    save_role_gamestate(buyer_id, buyer_gs)

# =========================
# Food offer (food vendor)
# =========================

def _ensure_counter_list(gs: dict, key: str) -> list:
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters
    lst = counters.get(key)
    if not isinstance(lst, list):
        lst = []
        counters[key] = lst
    return lst

def apply_food_purchase(*, seller_id: str, buyer_id: str, price: int):
    seller_gs = load_role_gamestate(seller_id)
    buyer_gs = load_role_gamestate(buyer_id)

    seller_st = seller_gs.get("status")
    if not isinstance(seller_st, dict):
        seller_st = {}
        seller_gs["status"] = seller_st

    buyer_st = buyer_gs.get("status")
    if not isinstance(buyer_st, dict):
        buyer_st = {}
        buyer_gs["status"] = buyer_st

    def _get_int(d, k):
        try:
            return int(d.get(k, 0))
        except Exception:
            return 0

    def _set_nonneg(d, k, v):
        try:
            v = int(v)
        except Exception:
            v = 0
        if v < 0:
            v = 0
        d[k] = v

    # buyer pays + gains stamina
    money = _get_int(buyer_st, "money")
    stamina = _get_int(buyer_st, "stamina")
    _set_nonneg(buyer_st, "money", money - int(price))
    _set_nonneg(buyer_st, "stamina", stamina + 1)

    # seller gains money
    s_money = _get_int(seller_st, "money")
    _set_nonneg(seller_st, "money", s_money + int(price))

    save_role_gamestate(seller_id, seller_gs)
    save_role_gamestate(buyer_id, buyer_gs)

def apply_food_help(*, buyer_id: str):
    buyer_gs = load_role_gamestate(buyer_id)
    buyer_st = buyer_gs.get("status")
    if not isinstance(buyer_st, dict):
        buyer_st = {}
        buyer_gs["status"] = buyer_st
    try:
        stamina = int(buyer_st.get("stamina", 0))
    except Exception:
        stamina = 0
    buyer_st["stamina"] = stamina + 1
    save_role_gamestate(buyer_id, buyer_gs)

def _record_food_offer_success(*, seller_id: str, eater_ids: list[str]):
    seller_gs = load_role_gamestate(seller_id)
    seller_st = seller_gs.get("status")
    if not isinstance(seller_st, dict):
        seller_st = {}
        seller_gs["status"] = seller_st

    # progress +1 per successful offer
    try:
        seller_st["progress"] = int(seller_st.get("progress", 0)) + 1
    except Exception:
        seller_st["progress"] = 1

    # counters
    counters = seller_gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        seller_gs["counters"] = counters
    counters["feed_successes"] = int(counters.get("feed_successes", 0) or 0) + 1

    eaters = _ensure_counter_list(seller_gs, "feed_eaters")
    for rid in eater_ids:
        if rid and rid not in eaters:
            eaters.append(rid)

    save_role_gamestate(seller_id, seller_gs)

def offer_food_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if not isinstance(players, list):
        players = []
    targets = [rid for rid in players if rid and rid != actor_id]
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        finn_free = bool(params.get("finn_free", False))
    except Exception:
        finn_free = False
    try:
        ignore_gate = bool(params.get("ignore_gate", False))
    except Exception:
        ignore_gate = False
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    try:
        min_eaters = int(params.get("min_eaters", 2))
    except Exception:
        min_eaters = 2
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": targets,
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "min_eaters": max(1, min_eaters),
        "finn_free": bool(finn_free),
        "ignore_gate": bool(ignore_gate),
        "params": params,
    }
    target_id = targets[0]
    return ("need_food_decision", {"target_id": target_id, "price": price}, pending)

def offer_food_decide(*, pending: dict, target_id: str, accept: bool):
    if not isinstance(pending, dict) or pending.get("type") != "offer_food":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "decide":
        return ("fail", {"reason": "bad_stage"}, None)

    if pending.get("force_accept"):
        accept = True

    remaining = pending.get("remaining", [])
    if not isinstance(remaining, list) or not remaining:
        return ("fail", {"reason": "no_targets"}, None)
    current = remaining.pop(0)
    if current != target_id:
        return ("fail", {"reason": "bad_target"}, None)

    seller_id = pending.get("actor_id")
    price = int(pending.get("price", 0) or 0)

    if accept:
        buyer_gs = load_role_gamestate(target_id)
        st = buyer_gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        try:
            money = int(st.get("money", 0))
        except Exception:
            money = 0
        try:
            curiosity = int(st.get("curiosity", 0))
        except Exception:
            curiosity = 0
        need_cur = 2 + int(pending.get("cost_plus", 0) or 0)
        finn_free = bool(pending.get("finn_free")) and target_id == "role_finn"
        ignore_gate = bool(pending.get("ignore_gate"))
        if not ignore_gate and (curiosity < need_cur or (not finn_free and money < price)):
            return ("need_help", {
                "action_type": "food",
                "seller_id": seller_id,
                "buyer_id": target_id,
                "price": price,
                "reason": "gate_failed",
                "pending": pending,
                "accept": True,
            }, None)
        if finn_free:
            # no money exchange
            add_status(target_id, "stamina", 1)
        else:
            apply_food_purchase(seller_id=seller_id, buyer_id=target_id, price=price)
        bonus = int(pending.get("bonus_stamina", 0) or 0)
        if bonus > 0:
            add_status(target_id, "stamina", bonus)
        pending["success_any"] = True
        pending.setdefault("eaters", []).append(target_id)
        stam_txt = f"+{1 + max(0, bonus)} stamina"
        if finn_free:
            pending.setdefault("logs", []).append(f"[FOOD] {target_id} accepted (free), {stam_txt}.")
        else:
            pending.setdefault("logs", []).append(f"[FOOD] {target_id} accepted and bought food (-{price} money, {stam_txt}).")
    else:
        pending.setdefault("logs", []).append(f"[FOOD] {target_id} declined.")

    # continue or finish
    if not remaining:
        eaters = pending.get("eaters", [])
        need = int(pending.get("min_eaters", 2) or 2)
        ok = len(eaters) >= need
        if ok:
            _record_food_offer_success(seller_id=seller_id, eater_ids=eaters)
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)

    next_id = remaining[0]
    kind = "need_food_force" if pending.get("force_accept") else "need_food_decision"
    return (kind, {"target_id": next_id, "price": price, "logs": pending.get("logs", [])}, pending)

def offer_food_help(*, pending: dict, buyer_id: str, helped: bool):
    if not isinstance(pending, dict) or pending.get("type") != "offer_food":
        return ("fail", {"reason": "bad_pending"}, None)
    seller_id = pending.get("actor_id")
    price = int(pending.get("price", 0) or 0)
    if helped:
        apply_food_help(buyer_id=buyer_id)
        bonus = int(pending.get("bonus_stamina", 0) or 0)
        if bonus > 0:
            add_status(buyer_id, "stamina", bonus)
        pending["success_any"] = True
        pending.setdefault("eaters", []).append(buyer_id)
        stam_txt = f"+{1 + max(0, bonus)} stamina"
        pending.setdefault("logs", []).append(f"[FOOD] {buyer_id} helped by volunteer ({stam_txt}).")
    else:
        pending.setdefault("logs", []).append(f"[FOOD] {buyer_id} not helped (failed).")
    # continue or finish
    remaining = pending.get("remaining", [])
    if not remaining:
        eaters = pending.get("eaters", [])
        need = int(pending.get("min_eaters", 2) or 2)
        ok = len(eaters) >= need
        if ok:
            _record_food_offer_success(seller_id=seller_id, eater_ids=eaters)
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
    next_id = remaining[0]
    kind = "need_food_force" if pending.get("force_accept") else "need_food_decision"
    return (kind, {"target_id": next_id, "price": price, "logs": pending.get("logs", [])}, pending)

def offer_food_lowest_force_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if not isinstance(players, list):
        players = []
    targets = list_lowest_curiosity_players(actor_id=actor_id, players=players)
    if not targets or len(targets) < 2:
        return ("done", {"ok": False, "reason": "not_enough_targets"}, None)
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": list(targets),
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "force_accept": True,
        "params": params,
    }
    target_id = targets[0]
    return ("need_food_force", {"target_id": target_id, "price": price}, pending)

# =========================
# Perform show (performer)
# =========================

def _record_perform_result(*, actor_id: str, success: bool, watchers: list[str], skip_stamina_cost: bool = False):
    # stamina cost always applies after result (unless skipped)
    if not skip_stamina_cost:
        add_status(actor_id, "stamina", -2 if success else -1)

    if not success:
        return

    # progress +1 per successful performance
    add_status(actor_id, "progress", 1)
    _add_counter(actor_id, "perform", 1)

    # optional: record watchers
    gs = load_role_gamestate(actor_id)
    counters = gs.get("counters")
    if not isinstance(counters, dict):
        counters = {}
        gs["counters"] = counters
    lst = counters.get("perform_watchers")
    if not isinstance(lst, list):
        lst = []
    for rid in watchers:
        if rid and rid not in lst:
            lst.append(rid)
    counters["perform_watchers"] = lst
    save_role_gamestate(actor_id, gs)

def perform_show_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    targets = _targets_excluding(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    actor_gs = load_role_gamestate(actor_id)
    stamina = _get_status_int(actor_gs, "stamina")
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": targets,
        "success_count": 0,
        "watchers": [],
        "params": params,
        "logs": [],
    }
    if stamina < 2:
        return ("need_help", {
            "action_type": "perform_start",
            "actor_id": actor_id,
            "reason": "need_stamina",
            "pending": pending,
        }, None)

    target_id = targets[0]
    return ("need_perform_decision", {"target_id": target_id}, pending)

def perform_show_decide(*, pending: dict, target_id: str, watch: bool):
    if not isinstance(pending, dict) or pending.get("type") != "perform_show":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "decide":
        return ("fail", {"reason": "bad_stage"}, None)

    remaining = pending.get("remaining", [])
    if not isinstance(remaining, list) or not remaining:
        return ("fail", {"reason": "no_targets"}, None)
    current = remaining.pop(0)
    if current != target_id:
        return ("fail", {"reason": "bad_target"}, None)

    forced = pending.get("forced_watchers")
    if isinstance(forced, list) and target_id in forced:
        watch = True

    if not watch:
        pending.setdefault("logs", []).append(f"[PERFORM] {target_id} declined.")
        # continue or finish
        if not remaining:
            need = int(pending.get("required_success", 2) or 2)
            ok = pending.get("success_count", 0) >= need
            _record_perform_result(
                actor_id=pending.get("actor_id", ""),
                success=ok,
                watchers=pending.get("watchers", []),
                skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
            )
            return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
        next_id = remaining[0]
        return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

    # watch -> choose benefit
    pending["stage"] = "benefit"
    pending["current"] = target_id
    return ("need_perform_benefit", {"target_id": target_id}, pending)

def _apply_perform_benefit(*, performer_id: str, watcher_id: str, choice: str, skip_cost: bool):
    if choice == "stamina_plus_curiosity_minus":
        add_status(watcher_id, "stamina", 1)
        if not skip_cost:
            add_status(watcher_id, "curiosity", -1)
    else:
        # money_minus_curiosity_plus
        if not skip_cost:
            add_status(watcher_id, "money", -1)
            add_status(performer_id, "money", 1)
        add_status(watcher_id, "curiosity", 1)

def perform_show_benefit(*, pending: dict, target_id: str, choice: str):
    if not isinstance(pending, dict) or pending.get("type") != "perform_show":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "benefit":
        return ("fail", {"reason": "bad_stage"}, None)
    if pending.get("current") != target_id:
        return ("fail", {"reason": "bad_target"}, None)

    watcher_gs = load_role_gamestate(target_id)
    curiosity = _get_status_int(watcher_gs, "curiosity")
    money = _get_status_int(watcher_gs, "money")
    if curiosity < 2:
        return ("need_help", {
            "action_type": "perform_watch",
            "actor_id": pending.get("actor_id", ""),
            "target_id": target_id,
            "choice": choice,
            "reason": "need_curiosity",
            "pending": pending,
        }, None)
    if choice == "money_minus_curiosity_plus" and money < 1:
        return ("need_help", {
            "action_type": "perform_watch",
            "actor_id": pending.get("actor_id", ""),
            "target_id": target_id,
            "choice": choice,
            "reason": "need_money",
            "pending": pending,
        }, None)

    _apply_perform_benefit(
        performer_id=pending.get("actor_id", ""),
        watcher_id=target_id,
        choice=choice,
        skip_cost=False,
    )
    pending["success_count"] = int(pending.get("success_count", 0)) + 1
    pending.setdefault("watchers", []).append(target_id)
    pending.setdefault("logs", []).append(f"[PERFORM] {target_id} watched ({choice}).")

    # continue or finish
    pending["stage"] = "decide"
    pending.pop("current", None)
    remaining = pending.get("remaining", [])
    if not remaining:
        need = int(pending.get("required_success", 2) or 2)
        ok = pending.get("success_count", 0) >= need
        _record_perform_result(
            actor_id=pending.get("actor_id", ""),
            success=ok,
            watchers=pending.get("watchers", []),
            skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
        )
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
    next_id = remaining[0]
    return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

def perform_show_help(*, pending: dict, target_id: str | None, choice: str | None, helped: bool):
    if not isinstance(pending, dict) or pending.get("type") != "perform_show":
        return ("fail", {"reason": "bad_pending"}, None)
    stage = pending.get("stage")

    if stage == "decide":
        # help for start gate
        if helped:
            # continue to first decision
            remaining = pending.get("remaining", [])
            if not remaining:
                need = int(pending.get("required_success", 2) or 2)
                ok = pending.get("success_count", 0) >= need
                _record_perform_result(
                    actor_id=pending.get("actor_id", ""),
                    success=ok,
                    watchers=pending.get("watchers", []),
                    skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
                )
                return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
            next_id = remaining[0]
            return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)
        pending.setdefault("logs", []).append("[PERFORM] Start gate failed (no help).")
        _record_perform_result(
            actor_id=pending.get("actor_id", ""),
            success=False,
            watchers=pending.get("watchers", []),
            skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
        )
        return ("done", {"ok": False, "logs": pending.get("logs", [])}, None)

    if stage == "benefit":
        if not target_id:
            target_id = pending.get("current")
        if not target_id:
            return ("fail", {"reason": "bad_target"}, None)
        if not helped:
            pending.setdefault("logs", []).append(f"[PERFORM] {target_id} not helped (failed).")
        else:
            _apply_perform_benefit(
                performer_id=pending.get("actor_id", ""),
                watcher_id=target_id,
                choice=choice or "stamina_plus_curiosity_minus",
                skip_cost=True,
            )
            pending["success_count"] = int(pending.get("success_count", 0)) + 1
            pending.setdefault("watchers", []).append(target_id)
            pending.setdefault("logs", []).append(f"[PERFORM] {target_id} helped and watched ({choice}).")

        # continue or finish
        pending["stage"] = "decide"
        pending.pop("current", None)
        remaining = pending.get("remaining", [])
        if not remaining:
            need = int(pending.get("required_success", 2) or 2)
            ok = pending.get("success_count", 0) >= need
            _record_perform_result(
                actor_id=pending.get("actor_id", ""),
                success=ok,
                watchers=pending.get("watchers", []),
                skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
            )
            return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
        next_id = remaining[0]
        return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

    return ("fail", {"reason": "bad_stage"}, None)

# =========================
# Food vendor gift orange (event effect)
# =========================

def gift_orange_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if not isinstance(players, list):
        players = []
    targets = [rid for rid in players if rid and rid != actor_id]
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)
    pending = {
        "type": "gift_orange",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "params": params,
    }
    return ("need_gift_target", {"targets": targets}, pending)

def gift_orange_choose_target(*, pending: dict, target_id: str):
    if not isinstance(pending, dict) or pending.get("type") != "gift_orange":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "choose_target":
        return ("fail", {"reason": "bad_stage"}, None)
    targets = pending.get("targets", [])
    if not isinstance(targets, list) or target_id not in targets:
        return ("need_gift_target", {"targets": targets, "error": "invalid_target"}, pending)
    actor_id = pending.get("actor_id", "")
    if not actor_id:
        return ("fail", {"reason": "missing_actor"}, None)
    add_status(target_id, "orange_product", 1)
    add_status(actor_id, "stamina", 1)
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)

# =========================
# Finn exchange product for orange
# =========================

def finn_exchange_orange_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if not isinstance(players, list):
        players = []
    actor_gs = load_role_gamestate(actor_id)
    if _get_status_int(actor_gs, "product") < 1:
        return ("done", {"ok": False, "reason": "need_product"}, None)
    targets = []
    for rid in players:
        if not rid or rid == actor_id:
            continue
        gs = load_role_gamestate(rid)
        if _get_status_int(gs, "orange_product") >= 1 or _get_status_int(gs, "orange_wear_product") >= 1:
            targets.append(rid)
    if not targets:
        return ("done", {"ok": False, "reason": "no_targets"}, None)
    pending = {
        "type": "finn_exchange",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "params": params,
    }
    return ("need_exchange_target", {"targets": targets}, pending)

def finn_exchange_orange_choose_target(*, pending: dict, target_id: str):
    if not isinstance(pending, dict) or pending.get("type") != "finn_exchange":
        return ("fail", {"reason": "bad_pending"}, None)
    if pending.get("stage") != "choose_target":
        return ("fail", {"reason": "bad_stage"}, None)
    targets = pending.get("targets", [])
    if not isinstance(targets, list) or target_id not in targets:
        return ("need_exchange_target", {"targets": targets, "error": "invalid_target"}, pending)
    actor_id = pending.get("actor_id", "")
    if not actor_id:
        return ("fail", {"reason": "missing_actor"}, None)

    target_gs = load_role_gamestate(target_id)
    if _get_status_int(target_gs, "orange_product") >= 1:
        add_status(target_id, "orange_product", -1)
    elif _get_status_int(target_gs, "orange_wear_product") >= 1:
        add_status(target_id, "orange_wear_product", -1)
        # clear orange-wear buffs if no longer wearing
        target_gs2 = load_role_gamestate(target_id)
        if _get_status_int(target_gs2, "orange_wear_product") < 1:
            clear_orange_wear_buffs(role_id=target_id)
    else:
        return ("done", {"ok": False, "reason": "target_no_orange"}, None)

    add_status(actor_id, "product", -1)
    add_status(actor_id, "orange_product", 1)
    add_status(target_id, "product", 1)
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)

# =========================
# Event: interesting target interactions
# =========================

def finn_trade_stamina_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_gs = load_role_gamestate(actor_id)
    has_product = _get_status_int(actor_gs, "product") >= 1
    has_orange = _get_status_int(actor_gs, "orange_product") >= 1
    if not has_product and not has_orange:
        return ("done", {"ok": False, "reason": "no_items"}, None)
    pending = {
        "type": "finn_trade_stamina",
        "stage": "choose_item",
        "actor_id": actor_id,
        "target_id": target_id,
        "options": [],
    }
    if has_product:
        pending["options"].append({"kind": "product", "label": "普通物品 -> 体力+1", "stamina": 1})
    if has_orange:
        pending["options"].append({"kind": "orange_product", "label": "橙色物品 -> 体力+3", "stamina": 3})
    if len(pending["options"]) == 1:
        pending["choice"] = pending["options"][0]
        return finn_trade_stamina_apply(pending=pending)
    return ("need_exchange_choice", {"options": pending["options"]}, pending)

def finn_trade_stamina_apply(*, pending: dict):
    if not isinstance(pending, dict) or pending.get("type") != "finn_trade_stamina":
        return ("fail", {"reason": "bad_pending"}, None)
    actor_id = pending.get("actor_id", "")
    target_id = pending.get("target_id", "")
    choice = pending.get("choice")
    if not actor_id or not target_id or not isinstance(choice, dict):
        return ("fail", {"reason": "missing_data"}, None)
    kind = choice.get("kind")
    stamina_gain = int(choice.get("stamina", 0) or 0)
    if kind not in ("product", "orange_product") or stamina_gain <= 0:
        return ("fail", {"reason": "bad_choice"}, None)
    target_gs = load_role_gamestate(target_id)
    if _get_status_int(target_gs, "stamina") < stamina_gain:
        return ("done", {"ok": False, "reason": "target_stamina_not_enough"}, None)
    # transfer item to target
    add_status(actor_id, kind, -1)
    add_status(target_id, kind, 1)
    # transfer stamina
    add_status(target_id, "stamina", -stamina_gain)
    add_status(actor_id, "stamina", stamina_gain)
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)

def finn_trade_stamina_choose(*, pending: dict, option_index: int):
    if not isinstance(pending, dict) or pending.get("type") != "finn_trade_stamina":
        return ("fail", {"reason": "bad_pending"}, None)
    options = pending.get("options", [])
    if not isinstance(options, list) or not options:
        return ("fail", {"reason": "no_options"}, None)
    if option_index < 0 or option_index >= len(options):
        return ("need_exchange_choice", {"options": options, "error": "invalid_choice"}, pending)
    pending["choice"] = options[option_index]
    return finn_trade_stamina_apply(pending=pending)

def tourist_photo_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "need_consent",
        "actor_id": actor_id,
        "targets": [target_id],
        "target_id": target_id,
        "params": params,
        "force_agree": True,
    }
    return ("need_consent", {"target_id": target_id}, pending)

def vendor_trade_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": [target_id],
        "force_agree": True,
    }
    return ("need_item", {"items": items}, pending)

def tourist_photo_lowest_stamina_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    targets = list_lowest_stamina_players(actor_id=actor_id, players=players)
    if not targets:
        return ("done", {"ok": False, "reason": "no_targets"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": targets,
        "target_id": None,
        "params": params,
        "force_agree": True,
    }
    return ("need_target", {"targets": targets}, pending)

def finn_take_curiosity_from_event_target(*, actor_id: str, players: list[str], params: dict | None = None):
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    add_status(target_id, "curiosity", -2)
    add_status(actor_id, "curiosity", 2)
    return ("done", {"ok": True, "actor_id": actor_id, "target_id": target_id}, None)

def tourist_photo_event_target_with_penalty_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    params = dict(params)
    params["reject_target_curiosity_delta"] = int(params.get("reject_target_curiosity_delta", -2) or -2)
    pending = {
        "type": "try_take_photo",
        "stage": "need_consent",
        "actor_id": actor_id,
        "targets": [target_id],
        "target_id": target_id,
        "params": params,
        "force_agree": False,
    }
    return ("need_consent", {"target_id": target_id}, pending)

def vendor_trade_event_target_force_if_no_orange_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    tgs = load_role_gamestate(target_id)
    force = _get_status_int(tgs, "orange_wear_product") < 1
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": [target_id],
        "force_agree": bool(force),
    }
    return ("need_item", {"items": items}, pending)

def food_offer_event_target_force_if_no_orange_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    tgs = load_role_gamestate(target_id)
    force = _get_status_int(tgs, "orange_wear_product") < 1
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": [target_id],
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "force_accept": bool(force),
        "min_eaters": 1,
        "params": params,
    }
    return ("need_food_force" if force else "need_food_decision", {"target_id": target_id, "price": price}, pending)

def finn_wear_from_target_if_wearing(*, actor_id: str, players: list[str], params: dict | None = None):
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    tgs = load_role_gamestate(target_id)
    if _get_status_int(tgs, "orange_wear_product") < 1:
        return ("done", {"ok": False, "reason": "target_not_wearing"}, None)
    ags = load_role_gamestate(actor_id)
    if _get_status_int(ags, "orange_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_product"}, None)
    add_status(actor_id, "orange_product", -1)
    add_status(actor_id, "orange_wear_product", 1)
    add_status(actor_id, "progress", 1)
    _add_counter(actor_id, "orange_worn", 1)
    return ("done", {"ok": True, "effect": "finn_wear_from_target_if_wearing"}, None)

def tourist_photo_event_target_if_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    if _get_status_int(load_role_gamestate(actor_id), "orange_wear_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_wear"}, None)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "need_consent",
        "actor_id": actor_id,
        "targets": [target_id],
        "target_id": target_id,
        "params": {},
        "force_agree": True,
    }
    return ("need_consent", {"target_id": target_id}, pending)

def vendor_trade_event_target_if_vendor_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") < 1:
        if _get_status_int(gs, "orange_product") >= 1:
            add_status(actor_id, "orange_product", -1)
            add_status(actor_id, "orange_wear_product", 1)
            return ("done", {"ok": True, "effect": "vendor_wear_orange_only"}, None)
        return ("done", {"ok": False, "reason": "need_orange_wear"}, None)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": [target_id],
        "force_agree": True,
        "ignore_gate": True,
    }
    return ("need_item", {"items": items}, pending)

def food_offer_event_target_if_vendor_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") < 1:
        if _get_status_int(gs, "orange_product") >= 1:
            add_status(actor_id, "orange_product", -1)
            add_status(actor_id, "orange_wear_product", 1)
            return ("done", {"ok": True, "effect": "food_vendor_wear_orange_only"}, None)
        return ("done", {"ok": False, "reason": "need_orange_wear"}, None)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": [target_id],
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "force_accept": True,
        "min_eaters": 1,
        "ignore_gate": True,
        "params": params,
    }
    return ("need_food_force", {"target_id": target_id, "price": price}, pending)

def vendor_trade_ignore_gate_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "ignore_gate": True,
    }
    return ("need_item", {"items": items}, pending)

def food_offer_ignore_gate_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    params = dict(params)
    params["ignore_gate"] = True
    return offer_food_start(actor_id=actor_id, players=players or [], params=params)

def performer_boost_and_perform(*, actor_id: str, players: list[str], params: dict | None = None):
    add_status(actor_id, "stamina", 2)
    return perform_show_start(actor_id=actor_id, players=players or [], params=params or {})

def finn_bonus_orange_if_watchers(*, actor_id: str, players: list[str], params: dict | None = None):
    watchers = get_event_watchers(actor_id=None)
    if len(watchers) >= 3:
        add_status(actor_id, "orange_product", 1)
        return ("done", {"ok": True, "effect": "finn_bonus_orange_if_watchers"}, None)
    return ("done", {"ok": False, "reason": "not_enough_watchers"}, None)

def tourist_photo_watchers_if_enough(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    watchers = get_event_watchers(actor_id=actor_id)
    if len(watchers) < 3:
        return ("done", {"ok": False, "reason": "not_enough_watchers"}, None)
    pending = {
        "type": "try_take_photo",
        "stage": "choose_target",
        "actor_id": actor_id,
        "targets": watchers,
        "target_id": None,
        "params": params,
        "force_if_target_wear": True,
    }
    return ("need_target", {"targets": watchers}, pending)

def vendor_trade_watchers_if_any(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    watchers = get_event_watchers(actor_id=actor_id)
    if len(watchers) < 1:
        return ("done", {"ok": False, "reason": "no_watchers"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    gs = load_role_gamestate(actor_id)
    force = _get_status_int(gs, "orange_wear_product") >= 1
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": watchers,
        "force_agree": bool(force),
    }
    return ("need_item", {"items": items}, pending)

def food_offer_watchers_if_any(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    watchers = get_event_watchers(actor_id=actor_id)
    if len(watchers) < 1:
        return ("done", {"ok": False, "reason": "no_watchers"}, None)
    target_id = watchers[0]
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    gs = load_role_gamestate(actor_id)
    force = _get_status_int(gs, "orange_wear_product") >= 1
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": [target_id],
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "force_accept": bool(force),
        "min_eaters": 1,
        "params": params,
    }
    return ("need_food_force" if force else "need_food_decision", {"target_id": target_id, "price": price}, pending)

def performer_auto_success_if_watchers(*, actor_id: str, players: list[str], params: dict | None = None):
    watchers = get_event_watchers(actor_id=actor_id)
    if len(watchers) >= 2:
        add_status(actor_id, "progress", 1)
        _add_counter(actor_id, "perform", 1)
        return ("done", {"ok": True, "effect": "performer_auto_success_if_watchers"}, None)
    return ("done", {"ok": False, "reason": "not_enough_watchers"}, None)

def performer_stage_with_forced_watcher(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "stamina") < 2:
        return ("done", {"ok": False, "reason": "need_stamina"}, None)
    remaining = [rid for rid in players if rid and rid != actor_id and rid != target_id]
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": remaining,
        "success_count": 1,  # forced watcher counts
        "watchers": [target_id],
        "params": params,
        "logs": [f"[PERFORM] {target_id} forced to watch (no cost)."],
        "required_success": 2,  # need at least one more watcher success
    }
    if not remaining:
        need = int(pending.get("required_success", 2) or 2)
        ok = pending.get("success_count", 0) >= need
        _record_perform_result(
            actor_id=actor_id,
            success=ok,
            watchers=pending.get("watchers", []),
            skip_stamina_cost=bool(pending.get("skip_stamina_cost")),
        )
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
    next_id = remaining[0]
    return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

def performer_stage_with_forced_watcher_no_stamina_cost(
    *,
    actor_id: str,
    players: list[str],
    params: dict | None = None,
):
    params, players = _norm_params_players(params, players)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "stamina") < 2:
        return ("done", {"ok": False, "reason": "need_stamina"}, None)
    remaining = [rid for rid in players if rid and rid != actor_id and rid != target_id]
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": remaining,
        "success_count": 1,  # forced watcher counts
        "watchers": [target_id],
        "params": params,
        "logs": [f"[PERFORM] {target_id} forced to watch (no cost)."],
        "required_success": 2,  # need at least one more watcher success
        "skip_stamina_cost": True,
    }
    if not remaining:
        need = int(pending.get("required_success", 2) or 2)
        ok = pending.get("success_count", 0) >= need
        _record_perform_result(
            actor_id=actor_id,
            success=ok,
            watchers=pending.get("watchers", []),
            skip_stamina_cost=True,
        )
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)
    next_id = remaining[0]
    return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

def performer_show_no_stamina_cost(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    targets = _targets_excluding(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    actor_gs = load_role_gamestate(actor_id)
    stamina = _get_status_int(actor_gs, "stamina")
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": targets,
        "success_count": 0,
        "watchers": [],
        "params": params,
        "logs": [],
        "skip_stamina_cost": True,
    }

    if stamina < 2:
        return ("need_help", {
            "action_type": "perform_start",
            "actor_id": actor_id,
            "reason": "need_stamina",
            "pending": pending,
        }, None)

    target_id = targets[0]
    return ("need_perform_decision", {"target_id": target_id}, pending)

def performer_show_required1_if_unworn_orange(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    actor_gs = load_role_gamestate(actor_id)
    orange_unworn = _get_status_int(actor_gs, "orange_product")
    kind, payload, pending = perform_show_start(actor_id=actor_id, players=players, params=params)
    if orange_unworn >= 1 and isinstance(pending, dict):
        pending["required_success"] = 1
        pending.setdefault("logs", []).append("[PERFORM] Unworn orange -> require 1 watcher.")
    return (kind, payload, pending)

def performer_show_force_selected_watcher_no_stamina_cost_if_target_has_both_orange(
    *,
    actor_id: str,
    players: list[str],
    params: dict | None = None,
):
    params, players = _norm_params_players(params, players)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    tgs = load_role_gamestate(target_id)
    if _get_status_int(tgs, "orange_product") < 1 or _get_status_int(tgs, "orange_wear_product") < 1:
        return ("done", {"ok": False, "reason": "target_not_both_orange"}, None)

    # start performance with forced watcher and no stamina cost
    targets = _targets_excluding(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    actor_gs = load_role_gamestate(actor_id)
    stamina = _get_status_int(actor_gs, "stamina")
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": [rid for rid in targets if rid != target_id],
        "success_count": 1,
        "watchers": [target_id],
        "params": params,
        "logs": [f"[PERFORM] {target_id} forced to watch (no cost)."],
        "required_success": 2,
        "skip_stamina_cost": True,
    }

    if stamina < 2:
        return ("need_help", {
            "action_type": "perform_start",
            "actor_id": actor_id,
            "reason": "need_stamina",
            "pending": pending,
        }, None)

    if not pending["remaining"]:
        ok = pending.get("success_count", 0) >= int(pending.get("required_success", 2) or 2)
        _record_perform_result(
            actor_id=actor_id,
            success=ok,
            watchers=pending.get("watchers", []),
            skip_stamina_cost=True,
        )
        return ("done", {"ok": ok, "logs": pending.get("logs", [])}, None)

    next_id = pending["remaining"][0]
    return ("need_perform_decision", {"target_id": next_id, "logs": pending.get("logs", [])}, pending)

def performer_show_force_watch_low_stamina(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    targets = _targets_excluding(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    actor_gs = load_role_gamestate(actor_id)
    stamina = _get_status_int(actor_gs, "stamina")
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": targets,
        "success_count": 0,
        "watchers": [],
        "params": params,
        "logs": [],
    }

    forced = []
    for rid in targets:
        gs = load_role_gamestate(rid)
        if _get_status_int(gs, "stamina") <= 3:
            forced.append(rid)
    if forced:
        pending["forced_watchers"] = forced
        pending.setdefault("logs", []).append("[PERFORM] Low-stamina watchers must watch.")

    if stamina < 2:
        return ("need_help", {
            "action_type": "perform_start",
            "actor_id": actor_id,
            "reason": "need_stamina",
            "pending": pending,
        }, None)

    target_id = targets[0]
    return ("need_perform_decision", {"target_id": target_id}, pending)

def performer_show_force_watch_lowest_stamina(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    targets = _targets_excluding(actor_id, players)
    if not targets:
        return ("fail", {"reason": "no_targets"}, None)

    actor_gs = load_role_gamestate(actor_id)
    stamina = _get_status_int(actor_gs, "stamina")
    pending = {
        "type": "perform_show",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": targets,
        "success_count": 0,
        "watchers": [],
        "params": params,
        "logs": [],
    }

    forced = list_lowest_stamina_players(actor_id=actor_id, players=players)
    forced = [rid for rid in forced if rid and rid in targets]
    if forced:
        pending["forced_watchers"] = forced
        pending.setdefault("logs", []).append("[PERFORM] Lowest-stamina watchers must watch.")

    if stamina < 2:
        return ("need_help", {
            "action_type": "perform_start",
            "actor_id": actor_id,
            "reason": "need_stamina",
            "pending": pending,
        }, None)

    target_id = targets[0]
    return ("need_perform_decision", {"target_id": target_id}, pending)

def performer_auto_success_if_stamina(*, actor_id: str, players: list[str], params: dict | None = None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "stamina") >= 2:
        add_status(actor_id, "progress", 1)
        _add_counter(actor_id, "perform", 1)
        return ("done", {"ok": True, "effect": "performer_auto_success_if_stamina"}, None)
    return ("done", {"ok": False, "reason": "need_stamina"}, None)

def performer_show_auto_success_if_wearing(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    actor_gs = load_role_gamestate(actor_id)
    orange_wear = _get_status_int(actor_gs, "orange_wear_product")
    kind, payload, pending = perform_show_start(actor_id=actor_id, players=players, params=params)
    if orange_wear >= 1 and isinstance(pending, dict):
        # force success regardless of watcher results
        pending["required_success"] = 0
        pending.setdefault("logs", []).append("[PERFORM] Wearing orange -> auto success.")
    return (kind, payload, pending)

def performer_wear_or_perform_required1(*, actor_id: str, players: list[str], params: dict | None = None):
    params, players = _norm_params_players(params, players)
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") >= 1:
        kind, payload, pending = perform_show_start(actor_id=actor_id, players=players, params=params)
        if isinstance(pending, dict):
            pending["required_success"] = 1
            pending.setdefault("logs", []).append("[PERFORM] Wearing orange -> require 1 watcher.")
        return (kind, payload, pending)
    if _get_status_int(gs, "orange_product") >= 1:
        add_status(actor_id, "orange_product", -1)
        add_status(actor_id, "orange_wear_product", 1)
        return ("done", {"ok": True, "effect": "performer_wear_or_perform_required1"}, None)
    return ("done", {"ok": False, "reason": "no_orange"}, None)

def performer_auto_success_if_lowest_curiosity_ge2_else_perform(
    *,
    actor_id: str,
    players: list[str],
    params: dict | None = None,
):
    params, players = _norm_params_players(params, players)
    g = load_current_game()
    lec = g.get("last_event_context")
    ids = []
    if isinstance(lec, dict):
        ids = lec.get("lowest_curiosity_targets") or []
    if isinstance(ids, list) and len([rid for rid in ids if rid]) >= 2:
        add_status(actor_id, "progress", 1)
        _add_counter(actor_id, "perform", 1)
        return ("done", {"ok": True, "effect": "performer_auto_success_if_lowest_curiosity_ge2"}, None)
    return perform_show_start(actor_id=actor_id, players=players, params=params)

def tourist_photo_auto_if_performer_wear(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if "role_performer" not in (players or []):
        return ("done", {"ok": False, "reason": "no_performer"}, None)
    pgs = load_role_gamestate("role_performer")
    if _get_status_int(pgs, "orange_wear_product") >= 1:
        apply_photo_progress_only(actor_id=actor_id, target_id="role_performer")
        return ("done", {"ok": True, "effect": "tourist_photo_auto_if_performer_wear"}, None)
    return ("done", {"ok": False, "reason": "performer_not_wearing"}, None)

def tourist_photo_or_swap_finn(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    if "role_performer" in (players or []):
        pgs = load_role_gamestate("role_performer")
        if _get_status_int(pgs, "orange_wear_product") >= 1:
            return try_take_photo_start(actor_id=actor_id, players=players or [], params=params)
    # otherwise, must swap with Finn
    if "role_finn" not in (players or []):
        return ("done", {"ok": False, "reason": "no_finn"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=True, only_product=False)
    target_opts = _get_exchange_item_options(role_id="role_finn", allow_wear=True, only_product=False)
    return swap_items_start(
        actor_id=actor_id,
        target_id="role_finn",
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=True,
    )

def vendor_trade_orange_if_wearing_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_wear"}, None)
    # only partners who have orange (wear or not)
    targets = []
    for rid in players or []:
        if not rid or rid == actor_id:
            continue
        rgs = load_role_gamestate(rid)
        if _get_status_int(rgs, "orange_product") >= 1 or _get_status_int(rgs, "orange_wear_product") >= 1:
            targets.append(rid)
    if not targets:
        return ("done", {"ok": False, "reason": "no_targets"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": targets,
        "force_agree": False,
        "force_if_partner_has_orange": True,
    }
    return ("need_item", {"items": items}, pending)

def food_price_double_global(*, actor_id: str, players: list[str], params: dict | None = None):
    apply_price_multiplier_global(factor=2)
    return ("done", {"ok": True, "effect": "food_price_double_global"}, None)

def vendor_trade_lowest_stamina_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    targets = list_lowest_stamina_players(actor_id=actor_id, players=players)
    if not targets:
        return ("done", {"ok": False, "reason": "no_targets"}, None)
    items = list_trade_items(actor_id=actor_id, load_gs_fn=load_role_gamestate)
    if not items:
        return ("done", {"ok": False, "reason": "no_trade_items"}, None)
    pending = {
        "type": "try_trade",
        "stage": "choose_item",
        "actor_id": actor_id,
        "item": None,
        "partner_id": None,
        "params": params,
        "partner_filter": targets,
        "force_agree": True,
        "reward_product_always": True,
    }
    return ("need_item", {"items": items}, pending)

def food_vendor_auto_feed_if_lowest_stamina(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    targets = list_lowest_stamina_players(actor_id=actor_id, players=players)
    if not targets or len(targets) < 2:
        return ("done", {"ok": False, "reason": "not_enough_targets"}, None)
    _record_food_offer_success(seller_id=actor_id, eater_ids=targets)
    return ("done", {"ok": True, "effect": "food_vendor_auto_feed"}, None)

def food_offer_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    seller_gs = load_role_gamestate(actor_id)
    price = compute_trade_price(seller_gs=seller_gs, item_key="food")
    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
    try:
        bonus = int(params.get("bonus_stamina", 0))
    except Exception:
        bonus = 0
    try:
        cost_plus = int(params.get("cost_plus", 0))
    except Exception:
        cost_plus = 0
    try:
        bonus += int(trade_state.get("food_bonus_stamina", 0) or 0)
    except Exception:
        pass
    try:
        cost_plus += int(trade_state.get("food_cost_plus", 0) or 0)
    except Exception:
        pass
    bonus = max(0, bonus)
    cost_plus = max(0, cost_plus)
    price = max(1, int(price) + cost_plus)
    pending = {
        "type": "offer_food",
        "stage": "decide",
        "actor_id": actor_id,
        "remaining": [target_id],
        "price": price,
        "success_any": False,
        "eaters": [],
        "bonus_stamina": bonus,
        "cost_plus": cost_plus,
        "force_accept": True,
        "min_eaters": 1,
        "params": params,
    }
    return ("need_food_force", {"target_id": target_id, "price": price}, pending)

def finn_swap_for_orange_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_gs = load_role_gamestate(actor_id)
    if _get_status_int(actor_gs, "curiosity") < 6:
        return ("done", {"ok": False, "reason": "need_curiosity"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=True, only_product=False)
    # target must provide orange (wear or not)
    target_opts = []
    tgs = load_role_gamestate(target_id)
    if _get_status_int(tgs, "orange_product") > 0:
        target_opts.append({"kind": "orange_product", "label": "橙色物品 x1"})
    if _get_status_int(tgs, "orange_wear_product") > 0:
        target_opts.append({"kind": "orange_wear_product", "label": "已佩戴橙色 x1"})
    return swap_items_start(
        actor_id=actor_id,
        target_id=target_id,
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=True,
    )

def tourist_swap_or_photo_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=False, only_product=True)
    tgs = load_role_gamestate(target_id)
    target_opts = []
    if _get_status_int(tgs, "orange_product") > 0:
        target_opts.append({"kind": "orange_product", "label": "橙色物品 x1"})
    if _get_status_int(tgs, "orange_wear_product") > 0:
        target_opts.append({"kind": "orange_wear_product", "label": "已佩戴橙色 x1"})
    return swap_items_start(
        actor_id=actor_id,
        target_id=target_id,
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=False,
        on_refuse={"type": "photo"},
    )

def vendor_swap_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=True, only_product=False)
    target_opts = _get_exchange_item_options(role_id=target_id, allow_wear=True, only_product=False)
    return swap_items_start(
        actor_id=actor_id,
        target_id=target_id,
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=False,
        on_refuse={"type": "money"},
    )

def food_vendor_swap_event_target_start(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=True, only_product=False)
    target_opts = _get_exchange_item_options(role_id=target_id, allow_wear=True, only_product=False)
    return swap_items_start(
        actor_id=actor_id,
        target_id=target_id,
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=False,
        on_refuse={"type": "money"},
    )

def performer_swap_event_target_plus_stamina(*, actor_id: str, players: list[str], params: dict | None = None):
    params = params if isinstance(params, dict) else {}
    # gain stamina regardless of swap success
    add_status(actor_id, "stamina", 2)
    target_id = get_event_selected_target(actor_id=actor_id)
    if not target_id:
        return ("done", {"ok": False, "reason": "no_target"}, None)
    actor_opts = _get_exchange_item_options(role_id=actor_id, allow_wear=True, only_product=False)
    target_opts = _get_exchange_item_options(role_id=target_id, allow_wear=True, only_product=False)
    return swap_items_start(
        actor_id=actor_id,
        target_id=target_id,
        actor_opts=actor_opts,
        target_opts=target_opts,
        force_agree=False,
        on_refuse=None,
    )

def try_trade_consent(
    *,
    pending: dict,
    agree: bool,
    load_gs_fn,
    save_gs_fn,
):
    """
    Step 3: 交易对象 同意 / 拒绝
    - 拒绝：直接失败，结束本轮
    - 同意：先检测门槛
        - 不通过：失败，结束本轮
        - 通过：执行交易，结束本轮
    Returns: (kind, payload, pending(None))
    """
    if pending.get("type") != "try_trade" or pending.get("stage") != "need_consent":
        return ("fail", {"reason": "bad_pending"}, None)

    seller_id = pending.get("actor_id")
    buyer_id = pending.get("partner_id")
    raw_item = pending.get("item")

    if isinstance(raw_item, dict):
        item_key = raw_item.get("kind")
    else:
        item_key = raw_item

    if not item_key:
        return ("fail", {"reason": "bad_item"}, None)
        if not seller_id or not buyer_id or not item:
            return ("fail", {"reason": "missing_data"}, None)

    # ❌ 对方拒绝
    if pending.get("force_agree"):
        agree = True

    if not agree:
        return ("done", {"ok": False, "reason": "rejected"}, None)

    # 读取双方状态
    seller_gs = load_gs_fn(seller_id)
    buyer_gs = load_gs_fn(buyer_id)

    # 1️⃣ 门槛检测
    if pending.get("ignore_gate"):
        price = compute_trade_price(seller_gs=seller_gs, item_key=item_key)
    else:
        ok, reason, price = can_trade(
            seller_gs=seller_gs,
            buyer_gs=buyer_gs,
            item_key=item_key,
        )

        # ❌ 门槛失败 → 本轮直接结束
        if not ok:
            if pending.get("reward_product_always"):
                add_status(seller_id, "product", 1)
            return (
                "need_help",
                {
                    "action_type": "trade",
                    "seller_id": seller_id,
                    "buyer_id": buyer_id,
                    "item_key": item_key,
                    "reason": reason,
                    "price": price,
                },
                None,
            )

    # 2️⃣ 门槛通过 → 执行交易
    apply_trade(
        seller_id=seller_id,
        buyer_id=buyer_id,
        item_key=item_key,
        price=price,
        load_gs_fn=load_gs_fn,
        save_gs_fn=save_gs_fn,
    )
    if pending.get("reward_product"):
        add_status(seller_id, "product", int(pending.get("reward_product", 0)))
    if pending.get("reward_product_always"):
        add_status(seller_id, "product", 1)
    # vendor orange-wear buff: consume on successful orange trade
    if pending.get("vendor_orange_force_once"):
        consume_vendor_orange_wear_buff(vendor_id=seller_id)

    return (
        "done",
        {
            "ok": True,
            "seller": seller_id,
            "buyer": buyer_id,
            "item": item_key,
            "price": price,
        },
        None,
    )

def compute_trade_price(*, seller_gs: dict, item_key: str) -> int:
    """
    item_key: "product" 或 "orange_product"
    价格来源：
    - seller_gs["trade_state"]["price_override"][item_key]  (优先)
    - 否则默认：product=1, orange_product=2
    再乘以 seller_gs["trade_state"]["price_mod"] (默认 1)
    """
    defaults = _load_trade_defaults()
    base_map = defaults.get("price_override", {"product": 1, "orange_product": 2, "food": 1})

    trade_state = seller_gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}

    override = trade_state.get("price_override")
    if not isinstance(override, dict):
        override = {}

    try:
        base = int(override.get(item_key, base_map.get(item_key, 1)))
    except Exception:
        base = base_map.get(item_key, 1)

    try:
        mod = int(trade_state.get("price_mod", 1))
    except Exception:
        mod = 1

    # apply global trade multiplier (if any)
    global_mod = 1
    g = load_current_game()
    gts = g.get("global_trade_state")
    if isinstance(gts, dict):
        try:
            global_mod = int(gts.get("price_mod", 1))
        except Exception:
            global_mod = 1

    price = base * max(1, mod) * max(1, global_mod)
    # vendor-specific orange wear buff: product price bonus
    if item_key == "product":
        trade_state = seller_gs.get("trade_state")
        if isinstance(trade_state, dict):
            try:
                bonus = int(trade_state.get("vendor_product_price_bonus", 0))
            except Exception:
                bonus = 0
            if bonus > 1:
                price = price * bonus
    return max(1, price)

def apply_price_multiplier_global(*, factor: int):
    g = load_current_game()
    gts = _ensure_global_trade_state(g)
    try:
        cur = int(gts.get("price_mod", 1))
    except Exception:
        cur = 1
    gts["price_mod"] = max(1, cur * int(factor))
    save_current_game(g)

def apply_price_multiplier_for_player(*, role_id: str, factor: int):
    gs = load_role_gamestate(role_id)
    trade_state = gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
        gs["trade_state"] = trade_state
    try:
        cur = int(trade_state.get("price_mod", 1))
    except Exception:
        cur = 1
    trade_state["price_mod"] = max(1, cur * int(factor))
    save_role_gamestate(role_id, gs)

def apply_vendor_orange_price_bonus(*, vendor_id: str, delta: int):
    gs = load_role_gamestate(vendor_id)
    trade_state = gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
        gs["trade_state"] = trade_state
    override = trade_state.get("price_override")
    if not isinstance(override, dict):
        override = {}
        trade_state["price_override"] = override
    try:
        cur = int(override.get("orange_product", 2))
    except Exception:
        cur = 2
    override["orange_product"] = max(1, cur + int(delta))
    save_role_gamestate(vendor_id, gs)

def apply_food_vendor_supply_boost(*, vendor_id: str, cost_plus: int, bonus_stamina: int):
    gs = load_role_gamestate(vendor_id)
    trade_state = gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
        gs["trade_state"] = trade_state
    try:
        cur_cost = int(trade_state.get("food_cost_plus", 0))
    except Exception:
        cur_cost = 0
    try:
        cur_bonus = int(trade_state.get("food_bonus_stamina", 0))
    except Exception:
        cur_bonus = 0
    trade_state["food_cost_plus"] = max(0, cur_cost + int(cost_plus))
    trade_state["food_bonus_stamina"] = max(0, cur_bonus + int(bonus_stamina))
    save_role_gamestate(vendor_id, gs)

def clear_orange_wear_buffs(*, role_id: str):
    """
    Clear buffs that are tied to wearing orange items.
    """
    gs = load_role_gamestate(role_id)
    trade_state = gs.get("trade_state")
    if not isinstance(trade_state, dict):
        return
    # current known buffs tied to orange wear
    for k in ("food_cost_plus", "food_bonus_stamina", "vendor_product_price_bonus", "vendor_orange_force_once"):
        if k in trade_state:
            trade_state[k] = 0
    # optional future container
    if "orange_buffs" in trade_state:
        trade_state["orange_buffs"] = {}
    save_role_gamestate(role_id, gs)

def apply_vendor_orange_wear_buff(*, vendor_id: str):
    gs = load_role_gamestate(vendor_id)
    trade_state = gs.get("trade_state")
    if not isinstance(trade_state, dict):
        trade_state = {}
        gs["trade_state"] = trade_state
    trade_state["vendor_product_price_bonus"] = 2
    trade_state["vendor_orange_force_once"] = 1
    save_role_gamestate(vendor_id, gs)

def consume_vendor_orange_wear_buff(*, vendor_id: str):
    # remove one worn orange and clear buff flags
    add_status(vendor_id, "orange_wear_product", -1)
    add_status(vendor_id, "orange_product", 1)
    gs = load_role_gamestate(vendor_id)
    trade_state = gs.get("trade_state")
    if isinstance(trade_state, dict):
        trade_state["vendor_product_price_bonus"] = 0
        trade_state["vendor_orange_force_once"] = 0
        save_role_gamestate(vendor_id, gs)

# =========================
# Role-card effect registry
# =========================

ROLECARD_EFFECT_REGISTRY = {}

def register_rolecard_effect(effect_id: str):
    """
    Decorator for registering role-card effects.
    """
    def wrapper(fn):
        ROLECARD_EFFECT_REGISTRY[effect_id] = fn
        return fn
    return wrapper


# =========================
# Dispatcher
# =========================

def run_rolecard_effect(
    effect_id: str,
    params: dict | None,
    *,
    actor_id: str,
    players: list[str] | None = None,
):
    """
    Execute role-specific effect from an event card.

    - GameFlow 不关心内部逻辑
    - 所有规则都在具体 effect function 里
    """
    if not isinstance(params, dict):
        params = {}

    fn = ROLECARD_EFFECT_REGISTRY.get(effect_id)
    if not fn:
        raise ValueError(f"Unknown rolecard effect: {effect_id}")

    return fn(
        actor_id=actor_id,
        params=params,
        players=players or [],
    )

@register_rolecard_effect("current_player_stat_plus")
def rc_current_player_stat_plus(*, actor_id: str, params: dict, players=None):
    """
    简单个人效果：当前玩家 +X
    """
    stat = params.get("stat")
    amount = int(params.get("amount", 1))

    if not stat:
        return

    add_status(actor_id, stat, amount)

@register_rolecard_effect("try_take_photo")
def rc_try_take_photo(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return try_take_photo_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("try_trade")
def rc_try_trade(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return try_trade_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_price_double_all")
def rc_vendor_price_double_all(*, actor_id: str, params: dict, players=None):
    apply_price_multiplier_global(factor=2)

@register_rolecard_effect("finn_wear_orange_plus_curiosity")
def rc_finn_wear_orange_plus_curiosity(*, actor_id: str, params: dict, players=None):
    ok, reason = apply_finn_wear_costs_and_progress(actor_id)
    if not ok:
        return ("need_help", {
            "action_type": "finn_wear",
            "actor_id": actor_id,
            "extra_curiosity": True,
            "reason": reason,
        }, None)

    # wear orange (reuse existing stat-plus effect)
    current_player_stat_plus(
        params={"stat": "orange_wear_product", "amount": 1},
        players=players or [],
        current_player_id=actor_id,
    )
    # extra effect: curiosity +1
    add_status(actor_id, "curiosity", 1)
    return ("done", {"ok": True, "effect": "finn_wear_orange_plus_curiosity"}, None)

@register_rolecard_effect("tourist_gift_finn_wear_and_photo")
def rc_tourist_gift_finn_wear_and_photo(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    if "role_finn" not in players:
        return ("done", {"ok": False, "reason": "finn_not_in_game"}, None)

    actor_gs = load_role_gamestate(actor_id)
    if _get_status_int(actor_gs, "orange_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_product"}, None)

    # actor gives one orange product to Finn (no gate, no stamina cost)
    add_status(actor_id, "orange_product", -1)
    apply_finn_wear_no_cost(actor_id="role_finn")

    # immediate photo success (no money/stamina cost)
    apply_photo_progress_only(actor_id=actor_id, target_id="role_finn")
    return ("done", {"ok": True, "effect": "tourist_gift_finn_wear_and_photo"}, None)

@register_rolecard_effect("vendor_orange_price_plus_2")
def rc_vendor_orange_price_plus_2(*, actor_id: str, params: dict, players=None):
    apply_vendor_orange_price_bonus(vendor_id=actor_id, delta=2)
    return ("done", {"ok": True, "effect": "vendor_orange_price_plus_2"}, None)

@register_rolecard_effect("food_vendor_orange_supply_boost")
def rc_food_vendor_orange_supply_boost(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_wear"}, None)
    try:
        cost_plus = int(params.get("cost_plus", 1))
    except Exception:
        cost_plus = 1
    try:
        bonus_stamina = int(params.get("bonus_stamina", 1))
    except Exception:
        bonus_stamina = 1
    apply_food_vendor_supply_boost(
        vendor_id=actor_id,
        cost_plus=cost_plus,
        bonus_stamina=bonus_stamina,
    )
    return ("done", {"ok": True, "effect": "food_vendor_orange_supply_boost"}, None)

@register_rolecard_effect("finn_wear_orange_no_cost")
def rc_finn_wear_orange_no_cost(*, actor_id: str, params: dict, players=None):
    apply_finn_wear_no_cost(actor_id=actor_id)
    return ("done", {"ok": True, "effect": "finn_wear_orange_no_cost"}, None)

@register_rolecard_effect("tourist_wear_then_photo")
def rc_tourist_wear_then_photo(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return wear_then_photo_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("finn_bonus_orange_if_wearing")
def rc_finn_bonus_orange_if_wearing(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_wear_product") >= 1:
        add_status(actor_id, "orange_product", 1)
    return ("done", {"ok": True, "effect": "finn_bonus_orange_if_wearing"}, None)

@register_rolecard_effect("tourist_photo_lowest_curiosity")
def rc_tourist_photo_lowest_curiosity(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_lowest_curiosity_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_lowest_curiosity")
def rc_vendor_trade_lowest_curiosity(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_lowest_curiosity_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_product_force")
def rc_vendor_trade_product_force(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_product_force_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("offer_food")
def rc_offer_food(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return offer_food_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("perform_show")
def rc_perform_show(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return perform_show_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_vendor_gift_orange")
def rc_food_vendor_gift_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return gift_orange_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_vendor_offer_lowest_force")
def rc_food_vendor_offer_lowest_force(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return offer_food_lowest_force_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("finn_exchange_product_for_orange")
def rc_finn_exchange_product_for_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_exchange_orange_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_product_for_curiosity")
def rc_tourist_product_for_curiosity(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "product") < 1:
        return ("done", {"ok": False, "reason": "need_product"}, None)
    add_status(actor_id, "product", -1)
    add_status(actor_id, "curiosity", 1)
    return ("done", {"ok": True, "effect": "tourist_product_for_curiosity"}, None)

@register_rolecard_effect("food_vendor_product_for_stamina")
def rc_food_vendor_product_for_stamina(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "product") < 1:
        return ("done", {"ok": False, "reason": "need_product"}, None)
    add_status(actor_id, "product", -1)
    add_status(actor_id, "stamina", 1)
    return ("done", {"ok": True, "effect": "food_vendor_product_for_stamina"}, None)

@register_rolecard_effect("vendor_wear_orange_buff_once")
def rc_vendor_wear_orange_buff_once(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_product"}, None)
    add_status(actor_id, "orange_product", -1)
    add_status(actor_id, "orange_wear_product", 1)
    apply_vendor_orange_wear_buff(vendor_id=actor_id)
    return ("done", {"ok": True, "effect": "vendor_wear_orange_buff_once"}, None)

@register_rolecard_effect("food_vendor_offer_no_cost")
def rc_food_vendor_offer_no_cost(*, actor_id: str, params: dict, players=None):
    # cancel the -1 stamina cost from role-effect trigger
    add_status(actor_id, "stamina", 1)
    players = players if isinstance(players, list) else []
    return offer_food_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_price_double_permanent")
def rc_vendor_price_double_permanent(*, actor_id: str, params: dict, players=None):
    apply_price_multiplier_for_player(role_id=actor_id, factor=2)
    return ("done", {"ok": True, "effect": "vendor_price_double_permanent"}, None)

@register_rolecard_effect("tourist_wear_orange_if_have_plus_curiosity")
def rc_tourist_wear_orange_if_have_plus_curiosity(*, actor_id: str, params: dict, players=None):
    gs = load_role_gamestate(actor_id)
    if _get_status_int(gs, "orange_product") < 1:
        return ("done", {"ok": False, "reason": "need_orange_product"}, None)
    add_status(actor_id, "orange_product", -1)
    add_status(actor_id, "orange_wear_product", 1)
    add_status(actor_id, "curiosity", 1)
    return ("done", {"ok": True, "effect": "tourist_wear_orange_if_have_plus_curiosity"}, None)

@register_rolecard_effect("finn_trade_stamina_by_item")
def rc_finn_trade_stamina_by_item(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_trade_stamina_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_event_target")
def rc_tourist_photo_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_event_target")
def rc_vendor_trade_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_offer_event_target")
def rc_food_offer_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_offer_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("finn_swap_for_orange_event_target")
def rc_finn_swap_for_orange_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_swap_for_orange_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_swap_or_photo_event_target")
def rc_tourist_swap_or_photo_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_swap_or_photo_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_swap_event_target")
def rc_vendor_swap_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_swap_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_vendor_swap_event_target")
def rc_food_vendor_swap_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_vendor_swap_event_target_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_swap_event_target_plus_stamina")
def rc_performer_swap_event_target_plus_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_swap_event_target_plus_stamina(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_lowest_stamina")
def rc_tourist_photo_lowest_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_lowest_stamina_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_lowest_stamina")
def rc_vendor_trade_lowest_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_lowest_stamina_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_vendor_auto_feed_lowest_stamina")
def rc_food_vendor_auto_feed_lowest_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_vendor_auto_feed_if_lowest_stamina(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("finn_take_curiosity_event_target")
def rc_finn_take_curiosity_event_target(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_take_curiosity_from_event_target(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_event_target_penalty")
def rc_tourist_photo_event_target_penalty(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_event_target_with_penalty_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_event_target_force_if_no_orange")
def rc_vendor_trade_event_target_force_if_no_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_event_target_force_if_no_orange_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_offer_event_target_force_if_no_orange")
def rc_food_offer_event_target_force_if_no_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_offer_event_target_force_if_no_orange_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("finn_bonus_orange_if_watchers")
def rc_finn_bonus_orange_if_watchers(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_bonus_orange_if_watchers(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_watchers_if_enough")
def rc_tourist_photo_watchers_if_enough(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_watchers_if_enough(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_watchers_if_any")
def rc_vendor_trade_watchers_if_any(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_watchers_if_any(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_offer_watchers_if_any")
def rc_food_offer_watchers_if_any(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_offer_watchers_if_any(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_auto_success_if_watchers")
def rc_performer_auto_success_if_watchers(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_auto_success_if_watchers(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_auto_success_if_stamina")
def rc_performer_auto_success_if_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_auto_success_if_stamina(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_show_auto_success_if_wearing")
def rc_performer_show_auto_success_if_wearing(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_auto_success_if_wearing(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_wear_or_perform_required1")
def rc_performer_wear_or_perform_required1(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_wear_or_perform_required1(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_auto_success_if_lowest_curiosity_ge2_else_perform")
def rc_performer_auto_success_if_lowest_curiosity_ge2_else_perform(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_auto_success_if_lowest_curiosity_ge2_else_perform(
        actor_id=actor_id,
        players=players,
        params=params,
    )

@register_rolecard_effect("tourist_photo_auto_if_performer_wear")
def rc_tourist_photo_auto_if_performer_wear(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_auto_if_performer_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_orange_if_wearing")
def rc_vendor_trade_orange_if_wearing(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_orange_if_wearing_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_price_double_global")
def rc_food_price_double_global(*, actor_id: str, params: dict, players=None):
    return food_price_double_global(actor_id=actor_id, players=players or [], params=params)

@register_rolecard_effect("performer_stage_with_forced_watcher")
def rc_performer_stage_with_forced_watcher(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_stage_with_forced_watcher(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_stage_with_forced_watcher_no_stamina_cost")
def rc_performer_stage_with_forced_watcher_no_stamina_cost(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_stage_with_forced_watcher_no_stamina_cost(
        actor_id=actor_id,
        players=players,
        params=params,
    )

@register_rolecard_effect("performer_show_force_watch_low_stamina")
def rc_performer_show_force_watch_low_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_force_watch_low_stamina(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_show_force_watch_lowest_stamina")
def rc_performer_show_force_watch_lowest_stamina(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_force_watch_lowest_stamina(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_show_no_stamina_cost")
def rc_performer_show_no_stamina_cost(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_no_stamina_cost(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_show_required1_if_unworn_orange")
def rc_performer_show_required1_if_unworn_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_required1_if_unworn_orange(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_show_force_selected_watcher_no_stamina_cost_if_target_has_both_orange")
def rc_performer_show_force_selected_watcher_no_stamina_cost_if_target_has_both_orange(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_show_force_selected_watcher_no_stamina_cost_if_target_has_both_orange(
        actor_id=actor_id,
        players=players,
        params=params,
    )

@register_rolecard_effect("finn_wear_from_target_if_wearing")
def rc_finn_wear_from_target_if_wearing(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return finn_wear_from_target_if_wearing(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_event_target_if_wear")
def rc_tourist_photo_event_target_if_wear(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_event_target_if_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_event_target_if_vendor_wear")
def rc_vendor_trade_event_target_if_vendor_wear(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_event_target_if_vendor_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_offer_event_target_if_vendor_wear")
def rc_food_offer_event_target_if_vendor_wear(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_offer_event_target_if_vendor_wear(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("tourist_photo_or_swap_finn")
def rc_tourist_photo_or_swap_finn(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return tourist_photo_or_swap_finn(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("vendor_trade_ignore_gate")
def rc_vendor_trade_ignore_gate(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return vendor_trade_ignore_gate_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("food_offer_ignore_gate")
def rc_food_offer_ignore_gate(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return food_offer_ignore_gate_start(actor_id=actor_id, players=players, params=params)

@register_rolecard_effect("performer_boost_and_perform")
def rc_performer_boost_and_perform(*, actor_id: str, params: dict, players=None):
    players = players if isinstance(players, list) else []
    return performer_boost_and_perform(actor_id=actor_id, players=players, params=params)
