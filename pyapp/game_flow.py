import os
import json
import random

from game_logic import load_current_game, load_player_gamestate
from core_logic import (
    load_role_by_id,
    check_draw_card_eligibility,
    apply_cost_option,
    get_draw_cost_config,
    update_winrate,
    save_gamestate,
)
from event_effects import (
    run_global_effect, save_current_game,
    run_rolecard_effect,
    try_take_photo_consent, try_take_photo_choose_target,
    try_trade_choose_item, try_trade_choose_partner, try_trade_consent,
)

# ======================
# Paths
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVENTS_DIR = os.path.join(ROOT, "data", "events")
GLOBAL_EVENT_DEFS = os.path.join(ROOT, "data", "global_defs.json")

# ======================
# IO helpers
# ======================

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else default
    except Exception:
        return default

def list_event_files():
    if not os.path.isdir(EVENTS_DIR):
        return []
    return [f for f in os.listdir(EVENTS_DIR) if f.endswith(".json")]

def load_event_effect_defs():
    obj = _load_json(GLOBAL_EVENT_DEFS, {"global_effect_defs": []})
    arr = obj.get("global_effect_defs", [])
    out = {}
    if isinstance(arr, list):
        for it in arr:
            if isinstance(it, dict) and it.get("id"):
                out[it["id"]] = it
    return out


# ==========================================================
# GameFlow
# ==========================================================
class GameFlow:
    """
    Responsibilities:
    - manage turn order
    - decide what actions are available
    - execute chosen action
    - log everything
    """

    def __init__(self):
        self.players: list[str] = []
        self.turn_index: int = 0
        self.logs: list[str] = []

        # OR draw: waiting for player choice
        self.pending_cost_choice = None
        self.pending_action = None
        self.pending_role_effect = None
        # event display defs (label_template etc.)
        self.event_defs = load_event_effect_defs()

    # ----------------------
    # Game lifecycle
    # ----------------------
    def start_game(self):
        cur = load_current_game()
        players = cur.get("players", [])
        if not isinstance(players, list) or not players:
            self.logs.append("[ERROR] No players in current game.")
            return None

        self.players = players
        self.turn_index = 0
        self.pending_cost_choice = None

        self.logs.append("=== Game Started ===")
        self.log_all_player_status()

        return self.start_turn()

    def is_game_over(self) -> bool:
        cur = load_current_game()
        return bool(cur.get("game_over"))
    
    def game_end(self):
        winners = self.calc_winners(self.players)
        if not winners:
            self.logs.append("\n=== GAME OVER ===")
            self.logs.append("No winner.")
        else:
            names = []
            for rid in winners:
                role = load_role_by_id(rid)
                names.append(role.get("name", rid))
            self.logs.append("\n=== GAME OVER ===")
            self.logs.append("Winner(s): " + ", ".join(names))
        self.log_all_player_status()
        update_winrate(self.players, winners)
        return {
            "game_over": True,
            "winners": winners,
        }

    # ----------------------
    # Turn handling
    # ----------------------
    def start_turn(self):
        # 🛑 先检查游戏是否结束
        cur = load_current_game()
        if cur.get("game_over"):
            return self.game_end()
        
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)

        self.logs.append(f"\n--- Turn: {role.get('name', rid)} ---")
        return self.player_turn()

    def end_turn(self):
        self.log_all_player_status() # 🔍 回合结束时，统一打印所有玩家状态
        self.turn_index += 1
        if self.turn_index >= len(self.players):
            self.turn_index = 0
        return self.start_turn()

    # ----------------------
    # Player turn entry
    # ----------------------
    def player_turn(self):
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)
        gs = load_player_gamestate(rid)

        can_draw, _ = check_draw_card_eligibility(role, gs)

        return {
            "role_id": rid,
            "role_name": role.get("name", rid),
            "can_draw": can_draw,
            "can_use_skill": True,   # stub for now
            "can_skip": True,
        }

    # ----------------------
    # Actions
    # ----------------------
    def skip_turn(self):
        self.logs.append("[TURN] Skip.")
        return self.end_turn()

    def use_skill(self):
        """
        Placeholder for active skill.
        """
        self.logs.append("[SKILL] (not implemented)")
        return self.end_turn()

    # ----------------------
    # Draw card flow
    # ----------------------
    def request_draw(self):
        """
        Called when user clicks 'Draw Card'.

        Returns:
        - ("next_turn", info_dict)
        - ("need_choice", {role_id, choices})
        """
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)
        gs = load_player_gamestate(rid)

        can_draw, payable = check_draw_card_eligibility(role, gs)
        if not can_draw:
            self.logs.append("[DRAW] Cannot draw -> treated as NO DRAW.")
            return ("next_turn", self.end_turn())

        logic, options = get_draw_cost_config(role)

        # THEN logic: auto choose first payable in order
        if logic == "THEN":
            chosen = None
            for opt in options:
                for p in payable:
                    if p["resource"] == opt["resource"] and p["delta"] == opt["delta"]:
                        chosen = opt
                        break
                if chosen:
                    break

            if not chosen:
                chosen = payable[0]

            apply_cost_option(rid, chosen)
            self.logs.append(f"[DRAW] Paid (THEN): {chosen['resource']}{chosen['delta']}")

            return ("next_turn", self.draw_card(rid))

        # OR logic: wait for UI choice
        self.pending_cost_choice = {
            "role_id": rid,
            "choices": payable,
        }
        self.logs.append(f"[DRAW] Choose cost (OR): {payable}")
        return ("need_choice", {"role_id": rid, "choices": payable})

    def choose_draw_cost(self, index: int):
        """
        Called after OR choice.
        """
        if not self.pending_cost_choice:
            return ("next_turn", self.start_turn())

        rid = self.pending_cost_choice["role_id"]
        choices = self.pending_cost_choice["choices"]

        if rid != self.players[self.turn_index]:
            self.pending_cost_choice = None
            return ("next_turn", self.start_turn())

        if index < 0 or index >= len(choices):
            return ("next_turn", self.start_turn())

        chosen = choices[index]
        apply_cost_option(rid, chosen)
        self.logs.append(f"[DRAW] Paid (OR): {chosen['resource']}{chosen['delta']}")

        self.pending_cost_choice = None
        return ("next_turn", self.draw_card(rid))

    # ----------------------
    #   不抽卡
    # ----------------------
    def request_no_draw_choice(self):
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)

        skill = role.get("active_skill")
        has_skill = isinstance(skill, dict) and str(skill.get("id", "")).strip()

        self.logs.append("[NO_DRAW] Choose: SKILL or SKIP")
        return {
            "role_id": rid,
            "role_name": role.get("name", rid),
            "ui_mode": "NO_DRAW_CHOICE",
            "has_skill": bool(has_skill),
        }
    

    def use_active_skill(self):
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)

        skill = role.get("active_skill")
        if not isinstance(skill, dict):
            self.logs.append("[SKILL] No active_skill.")
            self.log_all_player_status()
            return self.end_turn()

        effect_id = str(skill.get("id", "")).strip()
        params = skill.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if not effect_id:
            self.logs.append("[SKILL] Invalid skill id.")
            self.log_all_player_status()
            return self.end_turn()

        self.logs.append(f"[SKILL] Execute: {effect_id}")

        try:
            result = run_rolecard_effect(
                effect_id,
                params,
                actor_id=rid,
                players=self.players,
            )
        except Exception as e:
            self.logs.append(f"[SKILL] Execute failed: {e}")
            self.log_all_player_status()
            return self.end_turn()

        # 互动技能：交给 UI（不 end_turn）
        if isinstance(result, tuple) and len(result) == 3:
            kind, payload, pending = result
            payload = payload if isinstance(payload, dict) else {}

            if kind in ("need_target", "need_consent", "need_item", "need_partner"):
                self.pending_interactive = pending
                ptype = pending.get("type") if isinstance(pending, dict) else None

                if ptype == "try_take_photo":
                    if kind == "need_target":
                        return {
                            "role_id": rid,
                            "role_name": role.get("name", rid),
                            "ui_mode": "PHOTO_NEED_TARGET",
                            "targets": payload.get("targets", []),
                        }
                    if kind == "need_consent":
                        return {
                            "role_id": rid,
                            "role_name": role.get("name", rid),
                            "ui_mode": "PHOTO_NEED_CONSENT",
                            "target_id": payload.get("target_id", ""),
                        }

                if ptype == "try_trade":
                    if kind == "need_item":
                        return {
                            "role_id": rid,
                            "role_name": role.get("name", rid),
                            "ui_mode": "TRADE_NEED_ITEM",
                            "items": payload.get("items", []),
                        }
                    if kind == "need_partner":
                        return {
                            "role_id": rid,
                            "role_name": role.get("name", rid),
                            "ui_mode": "TRADE_NEED_PARTNER",
                            "partners": payload.get("partners", []),
                        }
                    if kind == "need_consent":
                        return {
                            "role_id": rid,
                            "role_name": role.get("name", rid),
                            "ui_mode": "TRADE_NEED_CONSENT",
                            "partner_id": payload.get("partner_id", ""),
                        }

            # 非互动 done/fail：走正常结束回合
            self.logs.append(f"[SKILL] {kind}: {payload}")

        # 非互动：打印状态 & 结束回合
        self.log_all_player_status()
        return self.end_turn()


    def skip_turn(self):
        self.logs.append("[SKIP] Do nothing.")
        self.log_all_player_status()
        return self.end_turn()
    
    # ----------------------
    # Draw event card
    # ----------------------
    def draw_card(self, current_player_id: str):
        result = self.draw_random_event_and_log(current_player_id)
        if not result:
            self.logs.append("[EVENT] draw failed.")
            self.log_all_player_status()
            return self.end_turn()
        ev = result["event"]
        effect_id = result["global_effect_id"]
        params = result["global_params"]
        run_global_effect(
            effect_id,
            params,
            players=self.players,
            current_player_id=current_player_id,
        )
        # 如果是“游戏立即结束”事件 → 写入 current_game.json
        if effect_id == "game_end_immediately":
            cur = load_current_game()
            cur["game_over"] = True
            cur["game_over_reason"] = "event_game_over"
            save_current_game(cur)
        
        # =======================================================
        # ✅【新增】抽卡 + 全局效果之后：给当前玩家“可选”个人效果
        # =======================================================
        role_effects = ev.get("role_effects", {})
        if isinstance(role_effects, dict):
            reff = role_effects.get(current_player_id)
        else:
            reff = None
        # 有个人效果：暂停回合，交给 UI 显示“触发/跳过”
        if isinstance(reff, dict):
            gs = load_player_gamestate(current_player_id)
            st = gs.get("status", {})
            stamina = int(st.get("stamina", 0)) if isinstance(st, dict) else 0
            can_trigger = stamina >= 1

            # 保存 pending，供 trigger/skip 按钮调用
            self.pending_role_effect = {
                "actor_id": current_player_id,
                "role_effect": reff,
            }

            self.logs.append("[ROLE_EFFECT] Trigger (-1 stamina) or skip?")

            role = load_role_by_id(current_player_id)
            return {
                "role_id": current_player_id,
                "role_name": role.get("name", current_player_id),
                "post_role_effect_choice": True,
                "can_trigger": can_trigger,
                "role_effect_type": str(reff.get("type", "")).strip(),
                "role_effect_id": str(reff.get("id", "")).strip(),
            }
        # =======================================================
        self.log_all_player_status()
        return self.end_turn()

    def draw_random_event_and_log(self, current_player_id: str):
        # 1) load deck state from current_game.json
        cur = load_current_game()
        drawn = cur.get("events_drawn", [])
        if not isinstance(drawn, list):
            drawn = []

        # 2) list all event files, remove already-drawn
        files = list_event_files()
        if not files:
            self.logs.append("[EVENT] No event files found.")
            return None

        remaining = [fn for fn in files if fn not in drawn]
        if not remaining:
            self.logs.append("[EVENT] No remaining event cards (all drawn this game).")
            return None

        # 3) draw one
        fn = random.choice(remaining)
        ev = _load_json(os.path.join(EVENTS_DIR, fn), {})

        # 4) mark as drawn (persist)
        drawn.append(fn)
        cur["events_drawn"] = drawn
        save_current_game(cur)

        # 5) log basic info
        name = ev.get("name", fn)
        self.logs.append(f'[EVENT] 抽到事件卡：「{name}」 ({fn})')

        # 6) parse global_effect
        ge = ev.get("global_effect")
        if not isinstance(ge, dict):
            self.logs.append("[EVENT] (No global effect)")
            return None

        effect_id = str(ge.get("id", "")).strip()
        event_params = ge.get("params", {})
        if not isinstance(event_params, dict):
            event_params = {}

        # 7) build exec_params by merging defaults (for display + execution一致)
        d = self.event_defs.get(effect_id)
        if d:
            tpl = d.get("label_template", effect_id)
            defaults = d.get("param_defaults", {})
            if not isinstance(defaults, dict):
                defaults = {}
            exec_params = dict(defaults)
            exec_params.update(event_params)

            # display with {curiosity} style
            display = {k: f"{{{v}}}" for k, v in exec_params.items()}
            try:
                text = tpl.format(**display)
            except Exception:
                text = tpl
            self.logs.append(f"[EVENT] 全局效果：{text}")
        else:
            exec_params = event_params
            self.logs.append(f"[EVENT] 全局效果：{effect_id}")

        # ✅ 返回整张事件卡 + 全局效果信息（后面 draw_card 需要 role_effects）
        return {
            "file": fn,
            "event": ev,
            "global_effect_id": effect_id,
            "global_params": exec_params,
        }
    
    # ----------------------
    # Logging
    # ----------------------
    def log_all_player_status(self):
        for rid in self.players:
            gs = load_player_gamestate(rid)
            st = gs.get("status", {})
            parts = [f"{k}={st.get(k,0)}" for k in sorted(st.keys())]
            self.logs.append(f"[{rid}] " + ", ".join(parts))

    def consume_logs(self):
        out = self.logs[:]
        self.logs.clear()
        return out
    
    # ----------------------
    # 胜率
    # ----------------------
    def calc_winners(self, players: list[str]) -> list[str]:
        # 1) explicit winners
        winners = []
        for rid in players:
            gs = load_player_gamestate(rid)
            if bool(gs.get("win_game")):
                winners.append(rid)

        if winners:
            return winners
        
        best = None
        best_ids = []

        for rid in players:
            gs = load_player_gamestate(rid)
            st = gs.get("status", {})
            if not isinstance(st, dict):
                st = {}

            try:
                prog = int(st.get("progress", 0))
            except Exception:
                prog = 0

            if best is None or prog > best:
                best = prog
                best_ids = [rid]
            elif prog == best:
                best_ids.append(rid)

        return best_ids
    
    def skip_role_effect(self):
        self.pending_role_effect = None
        self.log_all_player_status()
        return self.end_turn()
    
    # ----------------------
    # 拍照
    # ----------------------
    def trigger_role_effect(self):
        pr = self.pending_role_effect
        self.pending_role_effect = None

        if not isinstance(pr, dict):
            self.logs.append("[ROLE_EFFECT] No pending role effect.")
            return self.end_turn()

        actor_id = pr.get("actor_id")
        role_eff = pr.get("role_effect")

        if not actor_id or not isinstance(role_eff, dict):
            self.logs.append("[ROLE_EFFECT] Invalid role effect data.")
            return self.end_turn()

        # 1️⃣ 扣 1 体力
        apply_cost_option(actor_id, {"resource": "stamina", "delta": -1})
        self.logs.append("[ROLE_EFFECT] Paid: stamina -1")

        # 2️⃣ 调用配置里的 function
        effect_id = str(role_eff.get("id", "")).strip()
        params = role_eff.get("params", {})
        if not isinstance(params, dict):
            params = {}

        self.logs.append(f"[ROLE_EFFECT] Execute: {effect_id}")

        try:
            result = run_rolecard_effect(
                effect_id,
                params,
                actor_id=actor_id,
                players=self.players,
            )
        except Exception as e:
            self.logs.append(f"[ROLE_EFFECT] Execute failed: {e}")
            self.log_all_player_status()
            return self.end_turn()

        # 3️⃣ 处理返回值（互动/非互动）
        # 约定：互动函数返回 (kind, payload, pending)
        if isinstance(result, tuple) and len(result) == 3:
            kind, payload, pending = result
            payload = payload if isinstance(payload, dict) else {}

            # ---- need_target: UI 显示目标按钮 ----
            if kind == "need_target":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "PHOTO_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }

            # ---- need_consent: UI 显示同意/拒绝 ----
            if kind == "need_consent" and pending.get("type") == "try_take_photo":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "PHOTO_NEED_CONSENT",
                    "target_id": payload.get("target_id", ""),
                }
            
            # ---- need_item: 交易 - UI 显示物品按钮 ----
            if kind == "need_item":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "TRADE_NEED_ITEM",
                    "items": payload.get("items", []),
                }

            # ---- need_partner: 交易 - UI 显示对象按钮 ----
            if kind == "need_partner":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "TRADE_NEED_PARTNER",
                    "partners": payload.get("partners", []),
                }

            # ---- need_trade_consent: 交易 - UI 显示同意/拒绝 ----
            # （注意：这里仍然用 kind == "need_consent"，只是 payload 字段不同）
            if kind == "need_consent" and pending and pending.get("type") == "try_trade":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "TRADE_NEED_CONSENT",
                    "partner_id": payload.get("partner_id", ""),
                }

            # ---- done / fail: 直接结束回合 ----
            if kind in ("done", "fail"):
                self.pending_interactive = None
                self.logs.append(f"[ROLE_EFFECT] {kind}: {payload}")
                self.log_all_player_status()
                return self.end_turn()

        # 4️⃣ 非互动：默认当作执行完成，结束回合
        self.pending_interactive = None
        self.log_all_player_status()
        return self.end_turn()
    

    def photo_choose_target(self, target_id: str):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[PHOTO] No pending interactive.")
            return self.start_turn()

        kind, payload, new_pending = try_take_photo_choose_target(pending=pending, target_id=target_id)
        self.pending_interactive = new_pending

        if kind == "need_consent":
            payload = payload if isinstance(payload, dict) else {}
            actor_id = pending.get("actor_id", "")
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "PHOTO_NEED_CONSENT",
                "target_id": payload.get("target_id", ""),
            }

        # fail / need_target (invalid) / done
        self.logs.append(f"[PHOTO] {kind}: {payload}")
        if kind == "need_target":
            # 继续选目标
            payload = payload if isinstance(payload, dict) else {}
            actor_id = pending.get("actor_id", "")
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "PHOTO_NEED_TARGET",
                "targets": payload.get("targets", []),
            }

        self.log_all_player_status()
        return self.end_turn()


    def photo_consent(self, agree: bool):
        pending = self.pending_interactive
        self.pending_interactive = None
        if not isinstance(pending, dict):
            self.logs.append("[PHOTO] No pending interactive.")
            return self.start_turn()
        kind, payload, _ = try_take_photo_consent(
            pending=pending,
            agree=agree,
            load_gs_fn=load_player_gamestate,
            save_gs_fn=save_gamestate,  # 你需要有这个函数（下面说明）
        )
        self.logs.append(f"[PHOTO] {kind}: {payload}")
        self.log_all_player_status()
        return self.end_turn()
    
    # ----------------------
    # 交易
    # ----------------------
    def trade_choose_item(self, item_index: int):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[TRADE] No pending interactive.")
            return self.start_turn()

        kind, payload, new_pending = try_trade_choose_item(
            pending=pending,
            item_index=item_index,
            players=self.players,
        )
        self.pending_interactive = new_pending

        actor_id = pending.get("actor_id", "")

        # 进入选对象
        if kind == "need_partner":
            payload = payload if isinstance(payload, dict) else {}
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "TRADE_NEED_PARTNER",
                "partners": payload.get("partners", []),
            }

        # invalid_item -> 继续选物品
        if kind == "need_item":
            payload = payload if isinstance(payload, dict) else {}
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "TRADE_NEED_ITEM",
                "items": payload.get("items", []),
            }

        # fail / done
        self.logs.append(f"[TRADE] {kind}: {payload}")
        self.log_all_player_status()
        return self.end_turn()
    
    def trade_choose_partner(self, partner_id: str):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[TRADE] No pending interactive.")
            return self.start_turn()

        kind, payload, new_pending = try_trade_choose_partner(
            pending=pending,
            partner_id=partner_id,
            players=self.players,
        )
        self.pending_interactive = new_pending

        actor_id = pending.get("actor_id", "")

        # 进入同意/拒绝
        if kind == "need_consent":
            payload = payload if isinstance(payload, dict) else {}
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "TRADE_NEED_CONSENT",
                "partner_id": payload.get("partner_id", ""),
            }

        # invalid_partner -> 继续选对象
        if kind == "need_partner":
            payload = payload if isinstance(payload, dict) else {}
            return {
                "role_id": actor_id,
                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                "ui_mode": "TRADE_NEED_PARTNER",
                "partners": payload.get("partners", []),
            }

        # fail / done
        self.logs.append(f"[TRADE] {kind}: {payload}")
        self.log_all_player_status()
        return self.end_turn()
    
    def trade_consent(self, agree: bool):
        pending = self.pending_interactive
        self.pending_interactive = None

        if not isinstance(pending, dict):
            self.logs.append("[TRADE] No pending interactive.")
            return self.start_turn()
        kind, payload, _ = try_trade_consent(
            pending=pending,
            agree=agree,
            load_gs_fn=load_player_gamestate,
            save_gs_fn=save_gamestate,
        )
        self.logs.append(f"[TRADE] {kind}: {payload}")
        self.log_all_player_status()
        return self.end_turn()