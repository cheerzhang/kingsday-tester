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

def get_players_from_current_game():
    obj = load_current_game()
    players = obj.get("players", [])
    return players if isinstance(players, list) else []

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
        return (False, f"[SKILL] Finn wear requires curiosity >= {need_curiosity}.")
    if orange_product < 1:
        return (False, "[SKILL] Finn wear requires orange_product >= 1.")
    if stamina < 1:
        return (False, "[SKILL] Finn wear requires stamina >= 1.")
    return (True, "")

def apply_finn_wear_costs_and_progress(actor_id: str) -> tuple[bool, str]:
    gs = load_role_gamestate(actor_id)
    ok, reason = check_finn_wear_requirements(gs)
    if not ok:
        return (False, reason)
    add_status(actor_id, "stamina", -1)
    add_status(actor_id, "orange_product", -1)
    add_status(actor_id, "progress", 1)
    return (True, "")

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

# ======================
# Dispatcher
# ======================
EFFECT_REGISTRY = {
    "all_role_stat_plus": all_role_stat_plus,
    "current_player_stat_plus": current_player_stat_plus,
    "game_end_immediately": game_end_immediately,
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
            if orange_worn >= 1:
                targets.append(rid)
            continue
        if (orange_worn + orange_product) >= 1:
            targets.append(rid)
    return targets

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

    if not can_take_photo(actor_id, actor_gs, target_id, target_gs):
        return ("done", {"ok": False, "reason": "gate_failed"}, None)

    if not agree:
        return ("done", {"ok": False, "reason": "rejected"}, None)

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

    # 进入下一阶段
    pending["stage"] = "choose_partner"

    # 计算可交易对象
    partners = list_trade_partners(
        actor_id=actor_id,
        players=players or [],
        load_gs_fn=load_role_gamestate,
    )
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
    if not isinstance(players, list) or partner_id not in players or partner_id == actor_id:
        # 仍然停留在选对象阶段
        partners = list_trade_partners(
            actor_id=actor_id,
            players=players or [],
            load_gs_fn=load_role_gamestate,
        )
        return ("need_partner", {"partners": partners, "error": "invalid_partner"}, pending)

    # ✅ 记住对象
    pending["partner_id"] = partner_id

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

    _set_nonneg(seller_st, item_key, seller_item - 1)
    _set_nonneg(seller_st, "money", seller_money + price)
    _set_nonneg(seller_st, "stamina", seller_sta - 1)

    # ---- buyer changes ----
    buyer_item = _get_int(buyer_st, item_key)
    buyer_money = _get_int(buyer_st, "money")

    _set_nonneg(buyer_st, item_key, buyer_item + 1)
    _set_nonneg(buyer_st, "money", buyer_money - price)

    # ---- vendor progress (trade success) ----
    if seller_id == "role_vendor":
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
    if not agree:
        return ("done", {"ok": False, "reason": "rejected"}, None)

    # 读取双方状态
    seller_gs = load_gs_fn(seller_id)
    buyer_gs = load_gs_fn(buyer_id)

    # 1️⃣ 门槛检测
    ok, reason, price = can_trade(
        seller_gs=seller_gs,
        buyer_gs=buyer_gs,
        item_key=item_key,
    )

    # ❌ 门槛失败 → 本轮直接结束
    if not ok:
        return (
            "done",
            {
                "ok": False,
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
    base_map = defaults.get("price_override", {"product": 1, "orange_product": 2})

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
    return max(1, price)

# =========================
# Vendor price helpers
# =========================

def apply_price_multiplier_all_players(*, players: list[str], factor: int):
    if not isinstance(players, list):
        return
    try:
        factor = int(factor)
    except Exception:
        factor = 1
    if factor <= 1:
        return
    for rid in players:
        if not rid:
            continue
        gs = load_role_gamestate(rid)
        trade_state = gs.get("trade_state")
        if not isinstance(trade_state, dict):
            trade_state = {}
            gs["trade_state"] = trade_state
        try:
            mod = int(trade_state.get("price_mod", 1))
        except Exception:
            mod = 1
        trade_state["price_mod"] = max(1, mod * factor)
        save_role_gamestate(rid, gs)

def apply_price_multiplier_global(*, factor: int):
    g = load_current_game()
    gts = _ensure_global_trade_state(g)
    try:
        cur = int(gts.get("price_mod", 1))
    except Exception:
        cur = 1
    gts["price_mod"] = max(1, cur * int(factor))
    save_current_game(g)

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
        return ("done", {"ok": False, "reason": reason}, None)

    # wear orange (reuse existing stat-plus effect)
    current_player_stat_plus(
        params={"stat": "orange_wear_product", "amount": 1},
        players=players or [],
        current_player_id=actor_id,
    )
    # extra effect: curiosity +1
    add_status(actor_id, "curiosity", 1)
    return ("done", {"ok": True, "effect": "finn_wear_orange_plus_curiosity"}, None)
