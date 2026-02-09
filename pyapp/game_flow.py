import os
import json
import random

from game_logic import load_current_game, load_player_gamestate, is_game_over
from core_logic import (
    load_role_by_id,
    check_draw_card_eligibility,
    apply_cost_option,
    get_draw_cost_config,
    update_winrate,
    save_gamestate,
)
from victory_checks import VICTORY_REGISTRY
from event_effects import (
    run_global_effect, save_current_game,
    run_rolecard_effect,
    apply_finn_wear_costs_and_progress,
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
        self.current_event_info = None
        self.pending_help = None

        # OR draw: waiting for player choice
        self.pending_cost_choice = None
        self.pending_action = None
        self.pending_role_effect = None
        self.pending_event_target = None
        self.pending_watchers = None
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

        return self.start_turn()

    def is_game_over(self) -> bool:
        return is_game_over()

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
        if self.is_game_over():
            return self.game_end()
        
        rid = self.players[self.turn_index]
        role = load_role_by_id(rid)

        self.logs.append(f"\n--- Turn: {role.get('name', rid)} ---")
        return self.player_turn()

    def end_turn(self):
        self.log_all_player_status() # 🔍 回合结束时，统一打印所有玩家状态
        self.current_event_info = None
        try:
            cur = load_current_game()
            if isinstance(cur, dict) and "last_event_context" in cur:
                del cur["last_event_context"]
                save_current_game(cur)
        except Exception:
            pass
        if self._check_victory_and_mark_winners():
            return self.game_end()
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
        skill = role.get("active_skill")
        has_skill = isinstance(skill, dict) and str(skill.get("id", "")).strip()

        return {
            "role_id": rid,
            "role_name": role.get("name", rid),
            "can_draw": can_draw,
            "can_use_skill": bool(has_skill),
            "has_skill": bool(has_skill),
            "can_skip": True,
        }

    # ----------------------
    # Actions
    # ----------------------
    def skip_turn(self):
        self.logs.append("[TURN] Skip.")
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
            def _costs_equal(a: dict, b: dict) -> bool:
                ca = a.get("costs") or []
                cb = b.get("costs") or []
                if len(ca) != len(cb):
                    return False
                sa = sorted((c.get("resource"), int(c.get("delta", 0))) for c in ca)
                sb = sorted((c.get("resource"), int(c.get("delta", 0))) for c in cb)
                return sa == sb

            for opt in options:
                for p in payable:
                    if _costs_equal(p, opt):
                        chosen = opt
                        break
                if chosen:
                    break

            if not chosen:
                chosen = payable[0]

            apply_cost_option(rid, chosen)
            # display cost summary
            costs = chosen.get("costs", [])
            if costs:
                parts = [f"{c.get('resource')}{int(c.get('delta', 0))}" for c in costs]
                self.logs.append("[DRAW] Paid (THEN): " + ", ".join(parts))
            else:
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
        costs = chosen.get("costs", [])
        if costs:
            parts = [f"{c.get('resource')}{int(c.get('delta', 0))}" for c in costs]
            self.logs.append("[DRAW] Paid (OR): " + ", ".join(parts))
        else:
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
            return self.end_turn()

        effect_id = str(skill.get("id", "")).strip()
        params = skill.get("params", {})
        if not isinstance(params, dict):
            params = {}

        if not effect_id:
            self.logs.append("[SKILL] Invalid skill id.")
            return self.end_turn()

        # Finn active skill gate (wear orange product)
        if (
            rid == "role_finn"
            and effect_id == "current_player_stat_plus"
            and str(params.get("stat", "")).strip() == "orange_wear_product"
            and int(params.get("amount", 1)) == 1
        ):
            ok, reason = apply_finn_wear_costs_and_progress(rid)
            if not ok:
                if "role_volunteer" in self.players and reason != "need_orange_product":
                    self.pending_help = {
                        "action_type": "finn_wear",
                        "actor_id": rid,
                        "extra_curiosity": False,
                        "reason": reason,
                    }
                    return {
                        "role_id": rid,
                        "role_name": load_role_by_id(rid).get("name", rid),
                        "ui_mode": "HELP_DECISION",
                        "help_action": "finn_wear",
                    }
                msg = {
                    "need_curiosity": "[SKILL] Finn wear requires enough curiosity.",
                    "need_orange_product": "[SKILL] Finn wear requires orange_product >= 1.",
                    "need_stamina": "[SKILL] Finn wear requires stamina >= 1.",
                }.get(reason, str(reason))
                self.logs.append(msg)
                return self.end_turn()
            self.logs.append("[SKILL] Finn wear success: stamina -1, orange_product -1, orange_wear_product +1")

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

            if kind == "need_perform_decision":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "PERFORM_WATCH_DECIDE",
                    "target_id": payload.get("target_id", ""),
                }

            if kind == "need_perform_benefit":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "PERFORM_WATCH_BENEFIT",
                    "target_id": payload.get("target_id", ""),
                }

            if kind == "need_gift_target":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "GIFT_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }
            if kind == "need_exchange_target":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "EXCHANGE_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }
            if kind == "need_exchange_choice":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "EXCHANGE_NEED_CHOICE",
                    "options": payload.get("options", []),
                }

            if kind == "need_food_decision":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "FOOD_OFFER_DECIDE",
                    "target_id": payload.get("target_id", ""),
                    "price": payload.get("price", 0),
                }
            if kind == "need_food_force":
                self.pending_interactive = pending
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "FOOD_OFFER_FORCE",
                    "target_id": payload.get("target_id", ""),
                    "price": payload.get("price", 0),
                }

            if kind == "need_help":
                if "role_volunteer" not in self.players:
                    if payload.get("action_type") in ("perform_start", "perform_watch"):
                        from event_effects import perform_show_help
                        pending = payload.get("pending")
                        target_id = payload.get("target_id")
                        choice = payload.get("choice")
                        kind2, pl, new_pending = perform_show_help(
                            pending=pending,
                            target_id=target_id,
                            choice=choice,
                            helped=False,
                        )
                        if kind2 == "need_perform_decision":
                            self.pending_interactive = new_pending
                            if isinstance(pl, dict):
                                for line in pl.get("logs", []):
                                    self.logs.append(line)
                            return {
                                "role_id": rid,
                                "role_name": role.get("name", rid),
                                "ui_mode": "PERFORM_WATCH_DECIDE",
                                "target_id": pl.get("target_id", ""),
                            }
                        if isinstance(pl, dict):
                            for line in pl.get("logs", []):
                                self.logs.append(line)
                        return self.end_turn()
                    self.logs.append("[HELP] No volunteer in game.")
                    return self.end_turn()
                if payload.get("action_type") == "finn_wear" and payload.get("reason") == "need_orange_product":
                    self.logs.append("[HELP] Finn has no orange_product; cannot help.")
                    return self.end_turn()
                self.pending_help = payload
                return {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "ui_mode": "HELP_DECISION",
                    "help_action": payload.get("action_type", ""),
                }

            # 非互动 done/fail：走正常结束回合
            self.logs.append(f"[SKILL] {kind}: {payload}")

        # 非互动：打印状态 & 结束回合
        return self.end_turn()


    def skip_turn(self):
        self.logs.append("[SKIP] Do nothing.")
        return self.end_turn()
    
    # ----------------------
    # Draw event card
    # ----------------------
    def draw_card(self, current_player_id: str):
        result = self.draw_random_event_and_log(current_player_id)
        if not result:
            self.logs.append("[EVENT] draw failed.")
            self.current_event_info = None
            return self.end_turn()
        ev = result["event"]
        effect_id = result["global_effect_id"]
        params = result["global_params"]
        ge = ev.get("global_effect", {})
        label = ""
        if isinstance(ge, dict):
            label = str(ge.get("label", "")).strip()
        role_label = ""
        role_effects = ev.get("role_effects", {})
        if isinstance(role_effects, dict):
            reff = role_effects.get(current_player_id)
            if isinstance(reff, dict):
                role_label = str(reff.get("label", "")).strip()
        self.current_event_info = {
            "id": str(ev.get("id", "")).strip(),
            "name": str(ev.get("name", "")).strip(),
            "global_label": label,
            "role_label": role_label,
        }
        # special: global effect needs a chosen target
        if effect_id in ("choose_event_target", "choose_event_target_only", "choose_event_target_plus_stamina2", "choose_event_target_plus_curiosity_minus_stamina"):
            targets = [rid for rid in self.players if rid and rid != current_player_id]
            if not targets:
                self.logs.append("[EVENT] No valid target for event.")
            else:
                self.pending_event_target = {
                    "actor_id": current_player_id,
                    "event": ev,
                    "params": params,
                }
                return {
                    "role_id": current_player_id,
                    "role_name": load_role_by_id(current_player_id).get("name", current_player_id),
                    "ui_mode": "EVENT_NEED_TARGET",
                    "targets": targets,
                }
        if effect_id == "choose_watchers":
            targets = [rid for rid in self.players if rid]
            if not targets:
                self.logs.append("[EVENT] No valid watchers.")
            else:
                self.pending_watchers = {
                    "actor_id": current_player_id,
                    "event": ev,
                    "remaining": list(targets),
                    "watchers": [],
                }
                first_id = targets[0]
                return {
                    "role_id": current_player_id,
                    "role_name": load_role_by_id(current_player_id).get("name", current_player_id),
                    "ui_mode": "WATCH_DECIDE",
                    "target_id": first_id,
                }

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
        return self._post_event_role_effect(current_player_id, ev)
        # =======================================================
        return self.end_turn()

    def _post_event_role_effect(self, current_player_id: str, ev: dict):
        role_effects = ev.get("role_effects", {})
        if isinstance(role_effects, dict):
            reff = role_effects.get(current_player_id)
        else:
            reff = None
        if isinstance(reff, dict):
            self.pending_role_effect = {
                "actor_id": current_player_id,
                "role_effect": reff,
            }
            self.logs.append("[ROLE_EFFECT] Auto trigger (no cost).")
            return self.trigger_role_effect()
        return self.end_turn()

    def event_choose_target(self, target_id: str):
        pending = self.pending_event_target
        self.pending_event_target = None
        if not isinstance(pending, dict):
            self.logs.append("[EVENT] No pending event target.")
            return self.end_turn()
        actor_id = pending.get("actor_id", "")
        ev = pending.get("event", {})
        if not actor_id or not isinstance(ev, dict):
            self.logs.append("[EVENT] Invalid pending event.")
            return self.end_turn()
        if not target_id or target_id == actor_id:
            self.logs.append("[EVENT] Invalid target.")
            return self.end_turn()
        # apply target curiosity +1 if configured, and store context
        from event_effects import add_status, set_last_event_context
        ge = ev.get("global_effect", {}) if isinstance(ev, dict) else {}
        effect_id = str(ge.get("id", "")).strip()
        if effect_id == "choose_event_target":
            add_status(target_id, "curiosity", 1)
        if effect_id == "choose_event_target_plus_stamina2":
            add_status(target_id, "stamina", 2)
        if effect_id == "choose_event_target_plus_curiosity_minus_stamina":
            add_status(target_id, "curiosity", 1)
            from event_effects import _get_status_int
            tgs = load_player_gamestate(target_id)
            if _get_status_int(tgs, "stamina") > 0:
                add_status(target_id, "stamina", -1)
        set_last_event_context({"selected_target": target_id})
        # continue to role effect choice
        return self._post_event_role_effect(actor_id, ev)

    def watch_decide(self, target_id: str, watch: bool):
        pending = self.pending_watchers
        if not isinstance(pending, dict):
            self.logs.append("[EVENT] No pending watcher list.")
            return self.end_turn()
        remaining = pending.get("remaining", [])
        if not isinstance(remaining, list) or not remaining:
            self.pending_watchers = None
            return self.end_turn()
        current = remaining.pop(0)
        if current != target_id:
            self.logs.append("[EVENT] Invalid watcher target.")
            return self.end_turn()
        if watch:
            pending.setdefault("watchers", []).append(target_id)
            from event_effects import add_status
            add_status(target_id, "curiosity", 1)
        if not remaining:
            from event_effects import set_last_event_context
            set_last_event_context({"watchers": pending.get("watchers", [])})
            self.pending_watchers = None
            actor_id = pending.get("actor_id", "")
            ev = pending.get("event", {})
            return self._post_event_role_effect(actor_id, ev)
        next_id = remaining[0]
        self.pending_watchers = pending
        return {
            "role_id": pending.get("actor_id", ""),
            "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
            "ui_mode": "WATCH_DECIDE",
            "target_id": next_id,
        }

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

    def _check_victory_and_mark_winners(self) -> bool:
        winners: list[str] = []
        for rid in self.players:
            role = load_role_by_id(rid)
            victory = role.get("victory")
            if not isinstance(victory, dict):
                continue
            vid = str(victory.get("id", "")).strip()
            params = victory.get("params", {}) if isinstance(victory.get("params"), dict) else {}
            fn = VICTORY_REGISTRY.get(vid)
            if not fn:
                continue
            try:
                if fn(rid, params):
                    winners.append(rid)
            except Exception:
                continue

        if not winners:
            return False

        # mark winners in gamestate so calc_winners() picks them
        for rid in winners:
            gs = load_player_gamestate(rid)
            gs["win_game"] = True
            save_gamestate(rid, gs)

        cur = load_current_game()
        cur["game_over"] = True
        cur["game_over_reason"] = "victory"
        save_current_game(cur)
        return True
    
    def skip_role_effect(self):
        self.pending_role_effect = None
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

        # 1️⃣ 调用配置里的 function
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
            return self.end_turn()

        # 2️⃣ 处理返回值（互动/非互动）
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
            # ---- need_wear_target: UI 显示穿戴目标按钮 ----
            if kind == "need_wear_target":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "WEAR_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }
            # ---- need_food_decision: UI 显示供餐决策 ----
            if kind == "need_food_decision":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "FOOD_OFFER_DECIDE",
                    "target_id": payload.get("target_id", ""),
                    "price": payload.get("price", 0),
                }
            if kind == "need_food_force":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "FOOD_OFFER_FORCE",
                    "target_id": payload.get("target_id", ""),
                    "price": payload.get("price", 0),
                }
            # ---- need_perform_decision: UI 显示围观选择 ----
            if kind == "need_perform_decision":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "PERFORM_WATCH_DECIDE",
                    "target_id": payload.get("target_id", ""),
                }
            # ---- need_perform_benefit: UI 显示围观收益选择 ----
            if kind == "need_perform_benefit":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "PERFORM_WATCH_BENEFIT",
                    "target_id": payload.get("target_id", ""),
                }
            # ---- need_gift_target: UI 显示赠送对象 ----
            if kind == "need_gift_target":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "GIFT_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }
            if kind == "need_exchange_target":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "EXCHANGE_NEED_TARGET",
                    "targets": payload.get("targets", []),
                }
            if kind == "need_exchange_choice":
                self.pending_interactive = pending
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "EXCHANGE_NEED_CHOICE",
                    "options": payload.get("options", []),
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
                return self.end_turn()
            if kind == "need_help":
                if "role_volunteer" not in self.players:
                    if payload.get("action_type") in ("perform_start", "perform_watch"):
                        from event_effects import perform_show_help
                        pending = payload.get("pending")
                        target_id = payload.get("target_id")
                        choice = payload.get("choice")
                        kind2, pl, new_pending = perform_show_help(
                            pending=pending,
                            target_id=target_id,
                            choice=choice,
                            helped=False,
                        )
                        if kind2 == "need_perform_decision":
                            self.pending_interactive = new_pending
                            if isinstance(pl, dict):
                                for line in pl.get("logs", []):
                                    self.logs.append(line)
                            return {
                                "role_id": actor_id,
                                "role_name": load_role_by_id(actor_id).get("name", actor_id),
                                "ui_mode": "PERFORM_WATCH_DECIDE",
                                "target_id": pl.get("target_id", ""),
                            }
                        if isinstance(pl, dict):
                            for line in pl.get("logs", []):
                                self.logs.append(line)
                        return self.end_turn()
                    self.logs.append("[HELP] No volunteer in game.")
                    return self.end_turn()
                if payload.get("action_type") == "finn_wear" and payload.get("reason") == "need_orange_product":
                    self.logs.append("[HELP] Finn has no orange_product; cannot help.")
                    return self.end_turn()
                self.pending_help = payload
                return {
                    "role_id": actor_id,
                    "role_name": load_role_by_id(actor_id).get("name", actor_id),
                    "ui_mode": "HELP_DECISION",
                    "help_action": payload.get("action_type", ""),
                }

        # 4️⃣ 非互动：默认当作执行完成，结束回合
        self.pending_interactive = None
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
        if kind == "need_help":
            if "role_volunteer" not in self.players:
                self.logs.append("[HELP] No volunteer in game.")
                return self.end_turn()
            if payload.get("action_type") == "finn_wear" and payload.get("reason") == "need_orange_product":
                self.logs.append("[HELP] Finn has no orange_product; cannot help.")
                return self.end_turn()
            self.pending_help = payload
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "HELP_DECISION",
                "help_action": payload.get("action_type", ""),
            }
        self.logs.append(f"[PHOTO] {kind}: {payload}")
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
        if kind == "need_help":
            if "role_volunteer" not in self.players:
                self.logs.append("[HELP] No volunteer in game.")
                return self.end_turn()
            if payload.get("action_type") == "finn_wear" and payload.get("reason") == "need_orange_product":
                self.logs.append("[HELP] Finn has no orange_product; cannot help.")
                return self.end_turn()
            self.pending_help = payload
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "HELP_DECISION",
                "help_action": payload.get("action_type", ""),
            }
        self.logs.append(f"[TRADE] {kind}: {payload}")
        return self.end_turn()

    def food_offer_decide(self, target_id: str, accept: bool):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[FOOD] No pending offer.")
            return self.end_turn()
        from event_effects import offer_food_decide
        kind, payload, new_pending = offer_food_decide(
            pending=pending,
            target_id=target_id,
            accept=accept,
        )
        if kind == "need_help":
            if "role_volunteer" not in self.players:
                # continue without help
                from event_effects import offer_food_help
                pending = payload.get("pending")
                buyer_id = payload.get("buyer_id", "")
                kind2, pl, new_pending = offer_food_help(
                    pending=pending,
                    buyer_id=buyer_id,
                    helped=False,
                )
                if kind2 == "need_food_decision":
                    self.pending_interactive = new_pending
                    return {
                        "role_id": new_pending.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                        "ui_mode": "FOOD_OFFER_DECIDE",
                        "target_id": pl.get("target_id", ""),
                        "price": pl.get("price", 0),
                    }
                if kind2 == "need_food_force":
                    self.pending_interactive = new_pending
                    return {
                        "role_id": new_pending.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                        "ui_mode": "FOOD_OFFER_FORCE",
                        "target_id": pl.get("target_id", ""),
                        "price": pl.get("price", 0),
                    }
                return self.end_turn()
            self.pending_help = payload
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "HELP_DECISION",
                "help_action": payload.get("action_type", ""),
            }
        if kind == "need_food_decision":
            self.pending_interactive = new_pending
            for line in payload.get("logs", []) if isinstance(payload, dict) else []:
                self.logs.append(line)
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "FOOD_OFFER_DECIDE",
                "target_id": payload.get("target_id", ""),
                "price": payload.get("price", 0),
            }
        if kind == "need_food_force":
            self.pending_interactive = new_pending
            for line in payload.get("logs", []) if isinstance(payload, dict) else []:
                self.logs.append(line)
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "FOOD_OFFER_FORCE",
                "target_id": payload.get("target_id", ""),
                "price": payload.get("price", 0),
            }
        if isinstance(payload, dict):
            for line in payload.get("logs", []):
                self.logs.append(line)
        self.logs.append(f"[FOOD] {kind}: {payload}")
        return self.end_turn()

    def perform_watch_decide(self, target_id: str, watch: bool):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[PERFORM] No pending performance.")
            return self.end_turn()
        from event_effects import perform_show_decide
        kind, payload, new_pending = perform_show_decide(
            pending=pending,
            target_id=target_id,
            watch=watch,
        )
        if kind == "need_help":
            if "role_volunteer" not in self.players:
                from event_effects import perform_show_help
                pending2 = payload.get("pending")
                tid = payload.get("target_id")
                choice = payload.get("choice")
                kind2, pl, new_pending2 = perform_show_help(
                    pending=pending2,
                    target_id=tid,
                    choice=choice,
                    helped=False,
                )
                if kind2 == "need_perform_decision":
                    self.pending_interactive = new_pending2
                    for line in pl.get("logs", []) if isinstance(pl, dict) else []:
                        self.logs.append(line)
                    return {
                        "role_id": new_pending2.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending2.get("actor_id", "")).get("name", new_pending2.get("actor_id", "")),
                        "ui_mode": "PERFORM_WATCH_DECIDE",
                        "target_id": pl.get("target_id", ""),
                    }
                if isinstance(pl, dict):
                    for line in pl.get("logs", []):
                        self.logs.append(line)
                return self.end_turn()
            self.pending_help = payload
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "HELP_DECISION",
                "help_action": payload.get("action_type", ""),
            }
        if kind == "need_perform_benefit":
            self.pending_interactive = new_pending
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "PERFORM_WATCH_BENEFIT",
                "target_id": payload.get("target_id", ""),
            }
        if kind == "need_perform_decision":
            self.pending_interactive = new_pending
            for line in payload.get("logs", []) if isinstance(payload, dict) else []:
                self.logs.append(line)
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "PERFORM_WATCH_DECIDE",
                "target_id": payload.get("target_id", ""),
            }
        if isinstance(payload, dict):
            for line in payload.get("logs", []):
                self.logs.append(line)
        self.logs.append(f"[PERFORM] {kind}: {payload}")
        return self.end_turn()

    def perform_watch_benefit(self, target_id: str, choice: str):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[PERFORM] No pending performance.")
            return self.end_turn()
        from event_effects import perform_show_benefit
        kind, payload, new_pending = perform_show_benefit(
            pending=pending,
            target_id=target_id,
            choice=choice,
        )
        if kind == "need_help":
            if "role_volunteer" not in self.players:
                from event_effects import perform_show_help
                pending2 = payload.get("pending")
                tid = payload.get("target_id")
                choice2 = payload.get("choice")
                kind2, pl, new_pending2 = perform_show_help(
                    pending=pending2,
                    target_id=tid,
                    choice=choice2,
                    helped=False,
                )
                if kind2 == "need_perform_decision":
                    self.pending_interactive = new_pending2
                    for line in pl.get("logs", []) if isinstance(pl, dict) else []:
                        self.logs.append(line)
                    return {
                        "role_id": new_pending2.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending2.get("actor_id", "")).get("name", new_pending2.get("actor_id", "")),
                        "ui_mode": "PERFORM_WATCH_DECIDE",
                        "target_id": pl.get("target_id", ""),
                    }
                if isinstance(pl, dict):
                    for line in pl.get("logs", []):
                        self.logs.append(line)
                return self.end_turn()
            self.pending_help = payload
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "HELP_DECISION",
                "help_action": payload.get("action_type", ""),
            }
        if kind == "need_perform_decision":
            self.pending_interactive = new_pending
            for line in payload.get("logs", []) if isinstance(payload, dict) else []:
                self.logs.append(line)
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "PERFORM_WATCH_DECIDE",
                "target_id": payload.get("target_id", ""),
            }
        if isinstance(payload, dict):
            for line in payload.get("logs", []):
                self.logs.append(line)
        self.logs.append(f"[PERFORM] {kind}: {payload}")
        return self.end_turn()

    def gift_choose_target(self, target_id: str):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[GIFT] No pending gift.")
            return self.end_turn()
        from event_effects import gift_orange_choose_target
        kind, payload, new_pending = gift_orange_choose_target(
            pending=pending,
            target_id=target_id,
        )
        if kind == "need_gift_target":
            self.pending_interactive = new_pending
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "GIFT_NEED_TARGET",
                "targets": payload.get("targets", []),
            }
        self.pending_interactive = None
        self.logs.append(f"[GIFT] {kind}: {payload}")
        return self.end_turn()

    def exchange_choose_target(self, target_id: str):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[EXCHANGE] No pending exchange.")
            return self.end_turn()
        from event_effects import finn_exchange_orange_choose_target
        kind, payload, new_pending = finn_exchange_orange_choose_target(
            pending=pending,
            target_id=target_id,
        )
        if kind == "need_exchange_target":
            self.pending_interactive = new_pending
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "EXCHANGE_NEED_TARGET",
                "targets": payload.get("targets", []),
            }
        self.pending_interactive = None
        self.logs.append(f"[EXCHANGE] {kind}: {payload}")
        return self.end_turn()

    def exchange_choose_option(self, option_index: int):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[EXCHANGE] No pending exchange choice.")
            return self.end_turn()
        from event_effects import finn_trade_stamina_choose, swap_items_choose
        if pending.get("type") == "finn_trade_stamina":
            kind, payload, new_pending = finn_trade_stamina_choose(
                pending=pending,
                option_index=option_index,
            )
        else:
            kind, payload, new_pending = swap_items_choose(
                pending=pending,
                option_index=option_index,
            )
        if kind == "need_exchange_choice":
            self.pending_interactive = new_pending
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "EXCHANGE_NEED_CHOICE",
                "options": payload.get("options", []),
            }
        if kind == "need_exchange_consent":
            self.pending_interactive = new_pending
            return {
                "role_id": pending.get("actor_id", ""),
                "role_name": load_role_by_id(pending.get("actor_id", "")).get("name", pending.get("actor_id", "")),
                "ui_mode": "EXCHANGE_NEED_CONSENT",
                "target_id": payload.get("target_id", ""),
            }
        self.pending_interactive = None
        self.logs.append(f"[EXCHANGE] {kind}: {payload}")
        return self.end_turn()

    def exchange_consent(self, agree: bool):
        pending = self.pending_interactive
        if not isinstance(pending, dict):
            self.logs.append("[EXCHANGE] No pending exchange consent.")
            return self.end_turn()
        from event_effects import swap_items_consent
        kind, payload, new_pending = swap_items_consent(pending=pending, agree=agree)
        if kind == "need_consent" and isinstance(new_pending, dict) and new_pending.get("type") == "try_take_photo":
            self.pending_interactive = new_pending
            return {
                "role_id": new_pending.get("actor_id", ""),
                "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                "ui_mode": "PHOTO_NEED_CONSENT",
                "target_id": payload.get("target_id", ""),
            }
        self.pending_interactive = None
        self.logs.append(f"[EXCHANGE] {kind}: {payload}")
        return self.end_turn()

    def volunteer_help(self, agree: bool):
        if not self.pending_help:
            return self.end_turn()
        payload = self.pending_help
        action_type = payload.get("action_type", "")
        if not agree:
            self.logs.append("[HELP] Declined.")
            self.pending_help = None
            # continue food offer if applicable
            if action_type == "food":
                from event_effects import offer_food_help
                pending = payload.get("pending")
                buyer_id = payload.get("buyer_id", "")
                kind, pl, new_pending = offer_food_help(
                    pending=pending,
                    buyer_id=buyer_id,
                    helped=False,
                )
                if kind == "need_food_decision":
                    self.pending_interactive = new_pending
                    return {
                        "role_id": new_pending.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                        "ui_mode": "FOOD_OFFER_DECIDE",
                        "target_id": pl.get("target_id", ""),
                        "price": pl.get("price", 0),
                    }
                if kind == "need_food_force":
                    self.pending_interactive = new_pending
                    return {
                        "role_id": new_pending.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                        "ui_mode": "FOOD_OFFER_FORCE",
                        "target_id": pl.get("target_id", ""),
                        "price": pl.get("price", 0),
                    }
            if action_type in ("perform_start", "perform_watch"):
                from event_effects import perform_show_help
                pending = payload.get("pending")
                target_id = payload.get("target_id")
                choice = payload.get("choice")
                kind, pl, new_pending = perform_show_help(
                    pending=pending,
                    target_id=target_id,
                    choice=choice,
                    helped=False,
                )
                if kind == "need_perform_decision":
                    self.pending_interactive = new_pending
                    if isinstance(pl, dict):
                        for line in pl.get("logs", []):
                            self.logs.append(line)
                    return {
                        "role_id": new_pending.get("actor_id", ""),
                        "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                        "ui_mode": "PERFORM_WATCH_DECIDE",
                        "target_id": pl.get("target_id", ""),
                    }
            return self.end_turn()
        if "role_volunteer" not in self.players:
            self.logs.append("[HELP] No volunteer in game.")
            self.pending_help = None
            return self.end_turn()

        from event_effects import (
            apply_photo_success_no_costs,
            apply_trade_no_payment,
            record_volunteer_help,
            apply_finn_wear_no_cost,
            add_status,
        )

        self.pending_help = None
        if action_type == "photo":
            apply_photo_success_no_costs(
                actor_id=payload.get("actor_id", ""),
                target_id=payload.get("target_id", ""),
            )
            record_volunteer_help("role_volunteer", "photo")
            self.logs.append("[HELP] Photo completed by volunteer.")
        elif action_type == "trade":
            apply_trade_no_payment(
                seller_id=payload.get("seller_id", ""),
                buyer_id=payload.get("buyer_id", ""),
                item_key=payload.get("item_key", ""),
            )
            record_volunteer_help("role_volunteer", "trade")
            self.logs.append("[HELP] Trade completed by volunteer.")
        elif action_type == "finn_wear":
            actor_id = payload.get("actor_id", "")
            apply_finn_wear_no_cost(actor_id=actor_id)
            if payload.get("extra_curiosity"):
                add_status(actor_id, "curiosity", 1)
            record_volunteer_help("role_volunteer", "wear_orange")
            self.logs.append("[HELP] Finn wear completed by volunteer.")
        elif action_type == "food":
            from event_effects import offer_food_help
            pending = payload.get("pending")
            buyer_id = payload.get("buyer_id", "")
            kind, pl, new_pending = offer_food_help(
                pending=pending,
                buyer_id=buyer_id,
                helped=True,
            )
            record_volunteer_help("role_volunteer", "food")
            if kind == "need_food_decision":
                self.pending_interactive = new_pending
                self.logs.append("[HELP] Food offer continued by volunteer.")
                return {
                    "role_id": new_pending.get("actor_id", ""),
                    "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                    "ui_mode": "FOOD_OFFER_DECIDE",
                    "target_id": pl.get("target_id", ""),
                    "price": pl.get("price", 0),
                }
            if kind == "need_food_force":
                self.pending_interactive = new_pending
                self.logs.append("[HELP] Food offer continued by volunteer.")
                return {
                    "role_id": new_pending.get("actor_id", ""),
                    "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                    "ui_mode": "FOOD_OFFER_FORCE",
                    "target_id": pl.get("target_id", ""),
                    "price": pl.get("price", 0),
                }
            if isinstance(pl, dict):
                for line in pl.get("logs", []):
                    self.logs.append(line)
            self.logs.append("[HELP] Food offer completed by volunteer.")
        elif action_type in ("perform_start", "perform_watch"):
            from event_effects import perform_show_help
            pending = payload.get("pending")
            target_id = payload.get("target_id")
            choice = payload.get("choice")
            kind, pl, new_pending = perform_show_help(
                pending=pending,
                target_id=target_id,
                choice=choice,
                helped=True,
            )
            record_volunteer_help("role_volunteer", "perform")
            if kind == "need_perform_decision":
                self.pending_interactive = new_pending
                self.logs.append("[HELP] Performance continued by volunteer.")
                if isinstance(pl, dict):
                    for line in pl.get("logs", []):
                        self.logs.append(line)
                return {
                    "role_id": new_pending.get("actor_id", ""),
                    "role_name": load_role_by_id(new_pending.get("actor_id", "")).get("name", new_pending.get("actor_id", "")),
                    "ui_mode": "PERFORM_WATCH_DECIDE",
                    "target_id": pl.get("target_id", ""),
                }
            if isinstance(pl, dict):
                for line in pl.get("logs", []):
                    self.logs.append(line)
            self.logs.append("[HELP] Performance resolved by volunteer.")
        else:
            self.logs.append("[HELP] Unknown action.")
        return self.end_turn()
