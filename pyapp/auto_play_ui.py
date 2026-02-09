# pyapp/auto_play_ui.py
import os
import random
import tkinter as tk
from tkinter import ttk, messagebox

from game_logic import (
    REQUIRED_ROLE_IDS,
    init_game_runtime,
    load_all_roles_min,
    load_current_game,
    load_player_gamestate,
    is_game_over,
    reset_runtime,
)
from game_flow import GameFlow
from event_effects import compute_trade_price


class AutoPlayTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        # -----------------------
        # state
        # -----------------------
        self.roles = []
        self.vars = {}
        self.flow = None
        self.running = False
        self.info = None
        self.step_count = 0

        # 控制随机性：可选设置 seed（不填就是系统随机）
        self.seed_var = tk.StringVar(value="")
        self.delay_ms_var = tk.IntVar(value=50)     # 每步间隔（毫秒）
        self.max_steps_var = tk.IntVar(value=5000)  # 安全上限

        # -----------------------
        # header
        # -----------------------
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Auto Play (Tab4)", font=("Arial", 14, "bold")).pack(side="left")

        ttk.Label(head, text="Delay(ms):").pack(side="right", padx=(6, 2))
        ttk.Spinbox(head, from_=0, to=2000, textvariable=self.delay_ms_var, width=6).pack(side="right")

        ttk.Label(head, text="Max steps:").pack(side="right", padx=(12, 2))
        ttk.Spinbox(head, from_=10, to=999999, textvariable=self.max_steps_var, width=8).pack(side="right")

        ttk.Label(head, text="Seed:").pack(side="right", padx=(12, 2))
        ttk.Entry(head, textvariable=self.seed_var, width=12).pack(side="right")

        # -----------------------
        # buttons
        # -----------------------
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(10, 0))

        self.btn_reset = ttk.Button(btns, text="Reset Runtime", command=self.on_reset)
        self.btn_reset.pack(side="left")

        self.btn_start = ttk.Button(btns, text="Start Auto", command=self.on_start_auto)
        self.btn_start.pack(side="left", padx=(8, 0))

        self.btn_stop = ttk.Button(btns, text="Stop", command=self.on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(btns, textvariable=self.status_var, foreground="#666").pack(side="right")

        # -----------------------
        # roles list
        # -----------------------
        box = ttk.LabelFrame(self, text="Players (Finn + Tourist required)", padding=10)
        box.pack(fill="x", pady=(12, 10))
        self.roles_box = box

        # -----------------------
        # log
        # -----------------------
        log_box = ttk.LabelFrame(self, text="Auto Log", padding=10)
        log_box.pack(fill="both", expand=True)

        self.log_text = tk.Text(log_box, height=18, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        # init
        self.refresh_roles()

    # ==========================================================
    # UI helpers
    # ==========================================================
    def refresh_roles(self):
        for child in self.roles_box.winfo_children():
            child.destroy()

        self.roles = load_all_roles_min()
        self.vars = {}

        if not self.roles:
            ttk.Label(self.roles_box, text="No roles found in data/roles.").pack(anchor="w")
            return

        for r in self.roles:
            rid = r["id"]
            name = r["name"]
            v = tk.BooleanVar(value=(rid in REQUIRED_ROLE_IDS))
            self.vars[rid] = v

            row = ttk.Frame(self.roles_box)
            row.pack(fill="x", pady=2)

            cb = ttk.Checkbutton(row, text=f"{name} ({rid})", variable=v)
            cb.pack(side="left", anchor="w")

            # required roles cannot be unchecked
            if rid in REQUIRED_ROLE_IDS:
                cb.configure(state="disabled")

    def append_logs(self):
        if not self.flow:
            return
        lines = self.flow.consume_logs()
        for line in lines:
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def set_running(self, running: bool):
        self.running = running
        self.btn_start.configure(state=("disabled" if running else "normal"))
        self.btn_stop.configure(state=("normal" if running else "disabled"))

    # ==========================================================
    # buttons
    # ==========================================================
    def on_reset(self):
        if not messagebox.askyesno("Reset", "Delete runtime files and clear log?"):
            return
        reset_runtime()
        self.flow = None
        self.info = None
        self.step_count = 0
        self.log_text.delete("1.0", "end")
        self.status_var.set("Runtime cleared.")
        self.refresh_roles()

    def on_stop(self):
        self.set_running(False)
        self.status_var.set("Stopped.")

    def on_start_auto(self):
        if self.running:
            return

        chosen = [rid for rid, v in self.vars.items() if v.get()]
        for req in REQUIRED_ROLE_IDS:
            if req not in chosen:
                chosen.insert(0, req)

        if len(chosen) < 2:
            messagebox.showerror("Auto Play", "Need at least Finn + Tourist.")
            return

        # seed
        seed_txt = self.seed_var.get().strip()
        if seed_txt:
            try:
                random.seed(int(seed_txt))
            except Exception:
                random.seed(seed_txt)

        # reset runtime & init game
        reset_runtime()
        init_game_runtime(chosen)

        # start flow
        self.flow = GameFlow()
        self.info = self.flow.start_game()
        self.step_count = 0

        self.log_text.delete("1.0", "end")
        self.append_logs()

        self.set_running(True)
        self.status_var.set("Running...")
        self.after(1, self._auto_step)

    # ==========================================================
    # core: 自动“点按钮”
    # ==========================================================
    def _auto_step(self):
        if not self.running:
            return
        if not self.flow or not isinstance(self.info, dict):
            self.set_running(False)
            self.status_var.set("No flow/info.")
            return

        # safety
        self.step_count += 1
        if self.step_count > int(self.max_steps_var.get() or 0):
            self.set_running(False)
            self.status_var.set("Stopped (max steps reached).")
            return
        

        # game over?
        if is_game_over():
            # finalize game once: compute winners + update winrate + log
            if not (isinstance(self.info, dict) and self.info.get("game_over")):
                self.info = self.flow.game_end() if self.flow else self.info
            self.append_logs()
            self.set_running(False)
            self.status_var.set("Game Over.")
            return

        # 这一帧根据 info 决定“有哪些按钮”
        self.info = self._choose_and_apply(self.info)

        # 打印本步产生的 logs
        self.append_logs()

        # 下一步
        delay = int(self.delay_ms_var.get() or 0)
        self.after(max(0, delay), self._auto_step)

    def _choose_and_apply(self, info: dict) -> dict:
        """
        自利逻辑：
        - 自己优先赢、尽量不帮助别人
        - 不使用概率随机
        """
        ui_mode = info.get("ui_mode", "")

        def _status(role_id: str) -> dict:
            gs = load_player_gamestate(role_id)
            st = gs.get("status")
            return st if isinstance(st, dict) else {}

        def _ival(d: dict, key: str) -> int:
            try:
                return int(d.get(key, 0))
            except Exception:
                return 0

        def _progress(role_id: str) -> int:
            return _ival(_status(role_id), "progress")

        def _money(role_id: str) -> int:
            return _ival(_status(role_id), "money")

        def _curiosity(role_id: str) -> int:
            return _ival(_status(role_id), "curiosity")

        def _stamina(role_id: str) -> int:
            return _ival(_status(role_id), "stamina")

        def _orange_total(role_id: str) -> int:
            st = _status(role_id)
            return _ival(st, "orange_product") + _ival(st, "orange_wear_product")

        def _pick_target_high_progress(targets: list[str]) -> str | None:
            if not targets:
                return None
            return max(targets, key=lambda rid: (_progress(rid), _money(rid), _curiosity(rid)))

        def _pick_target_low_progress(targets: list[str]) -> str | None:
            if not targets:
                return None
            return min(targets, key=lambda rid: (_progress(rid), _money(rid), _curiosity(rid)))

        def _pick_trade_partner(partners: list[str]) -> str | None:
            if not partners:
                return None
            return max(partners, key=lambda rid: (_money(rid), _curiosity(rid), _progress(rid)))

        def _pick_target_orange_rich(targets: list[str]) -> str | None:
            if not targets:
                return None
            return max(targets, key=lambda rid: (_orange_total(rid), _progress(rid)))

        def _value_item_kind(kind: str) -> int:
            return {"product": 1, "orange_product": 2, "orange_wear_product": 3}.get(kind, 0)

        def _pick_exchange_option(options: list[dict], prefer_high: bool) -> int | None:
            if not options:
                return None
            scored = []
            for i, opt in enumerate(options):
                kind = str(opt.get("kind", "")).strip()
                scored.append((i, _value_item_kind(kind)))
            if prefer_high:
                return max(scored, key=lambda t: t[1])[0]
            return min(scored, key=lambda t: t[1])[0]

        def _choose_trade_item_index(items: list[dict], seller_id: str) -> int | None:
            if not items:
                return None
            seller_gs = load_player_gamestate(seller_id)
            def _price(it):
                kind = it.get("kind")
                if not kind:
                    return 0
                return compute_trade_price(seller_gs=seller_gs, item_key=kind)
            return max(range(len(items)), key=lambda i: _price(items[i]))

        def _choose_draw_cost_index(choices: list[dict], role_id: str) -> int | None:
            if not choices:
                return None
            st = _status(role_id)
            weights = {
                "stamina": 3,
                "curiosity": 3,
                "money": 2,
                "orange_product": 2,
                "orange_wear_product": 2,
                "product": 1,
            }
            def _score(choice: dict) -> int:
                costs = choice.get("costs", [])
                score = 0
                for k, w in weights.items():
                    score += _ival(st, k) * w
                for c in costs:
                    if not isinstance(c, dict):
                        continue
                    res = str(c.get("resource", "")).strip()
                    delta = int(c.get("delta", 0))
                    score += delta * weights.get(res, 0)
                return score
            return max(range(len(choices)), key=lambda i: _score(choices[i]))

        def _decide_photo_consent(target_id: str) -> bool:
            if not target_id:
                return False
            pending = getattr(self.flow, "pending_interactive", {}) or {}
            if pending.get("force_agree"):
                return True
            st = _status(target_id)
            if target_id == "role_finn":
                return True
            if pending.get("force_if_target_wear"):
                if _ival(st, "orange_wear_product") >= 1:
                    return True
            params = pending.get("params", {}) if isinstance(pending.get("params"), dict) else {}
            try:
                reject_delta = int(params.get("reject_target_curiosity_delta", 0))
            except Exception:
                reject_delta = 0
            if reject_delta < 0 and (_curiosity(target_id) + reject_delta) < 2:
                return True
            return _money(target_id) <= 0

        def _decide_trade_consent(target_id: str) -> bool:
            pending = getattr(self.flow, "pending_interactive", {}) or {}
            if pending.get("force_agree"):
                return True
            if not target_id:
                return False
            seller_id = pending.get("actor_id")
            item = pending.get("item")
            item_key = item.get("kind") if isinstance(item, dict) else item
            if not item_key or not seller_id:
                return False
            seller_gs = load_player_gamestate(seller_id)
            price = compute_trade_price(seller_gs=seller_gs, item_key=item_key)
            buyer_money = _money(target_id)
            if buyer_money <= price:
                return False
            if item_key == "orange_product":
                return _orange_total(target_id) < 1
            if item_key == "product":
                return _ival(_status(target_id), "product") < 1
            return False

        def _decide_exchange_consent(target_id: str) -> bool:
            pending = getattr(self.flow, "pending_interactive", {}) or {}
            if pending.get("force_agree"):
                return True
            ac = pending.get("actor_choice") or {}
            tc = pending.get("target_choice") or {}
            receive = ac.get("kind")
            give = tc.get("kind")
            return _value_item_kind(receive) >= _value_item_kind(give)

        def _decide_food_accept(target_id: str) -> bool:
            pending = getattr(self.flow, "pending_interactive", {}) or {}
            if pending.get("force_accept"):
                return True
            if not target_id:
                return False
            st = _status(target_id)
            price = int(pending.get("price", 0) or 0)
            need_cur = 2 + int(pending.get("cost_plus", 0) or 0)
            finn_free = bool(pending.get("finn_free")) and target_id == "role_finn"
            if _ival(st, "curiosity") < need_cur:
                return False
            if not finn_free and _ival(st, "money") < price:
                return False
            # 只在体力偏低时接受
            return _ival(st, "stamina") <= 1

        def _decide_perform_watch(target_id: str) -> bool:
            if not target_id:
                return False
            st = _status(target_id)
            if _ival(st, "curiosity") < 2:
                return False
            if _ival(st, "stamina") <= 1:
                return True
            if _ival(st, "curiosity") <= 2 and _ival(st, "money") >= 1:
                return True
            return False

        def _choose_perform_benefit(target_id: str) -> str:
            st = _status(target_id)
            if _ival(st, "stamina") <= 1 and _ival(st, "curiosity") > 2:
                return "stamina_plus_curiosity_minus"
            if _ival(st, "money") >= 1 and _ival(st, "curiosity") <= 2:
                return "money_minus_curiosity_plus"
            return "stamina_plus_curiosity_minus"

        def _decide_watch_list(target_id: str) -> bool:
            return _curiosity(target_id) <= 1

        def _decide_help(action_type: str) -> bool:
            gs = load_player_gamestate("role_volunteer")
            counters = gs.get("counters")
            if not isinstance(counters, dict):
                counters = {}
            types = counters.get("help_types")
            if not isinstance(types, list):
                types = []
            return action_type not in types

        def _exchange_choose() -> dict:
            opts = info.get("options", [])
            if not opts:
                return self.flow.end_turn()
            prefer_high = (getattr(self.flow, "pending_interactive", {}) or {}).get("stage") == "choose_target_item"
            idx = _pick_exchange_option(opts, prefer_high=prefer_high)
            if idx is None:
                return self.flow.end_turn()
            return self.flow.exchange_choose_option(idx)

        actions = {
            "PHOTO_NEED_TARGET": lambda: self.flow.photo_choose_target(_pick_target_high_progress(info.get("targets", [])) or ""),
            "WEAR_NEED_TARGET": lambda: self.flow.photo_choose_target(_pick_target_high_progress(info.get("targets", [])) or ""),
            "PHOTO_NEED_CONSENT": lambda: self.flow.photo_consent(_decide_photo_consent(info.get("target_id", ""))),
            "HELP_DECISION": lambda: self.flow.volunteer_help(_decide_help(info.get("help_action", ""))),
            "FOOD_OFFER_DECIDE": lambda: self.flow.food_offer_decide(info.get("target_id", ""), _decide_food_accept(info.get("target_id", ""))),
            "FOOD_OFFER_FORCE": lambda: self.flow.food_offer_decide(info.get("target_id", ""), True),
            "PERFORM_WATCH_DECIDE": lambda: self.flow.perform_watch_decide(info.get("target_id", ""), _decide_perform_watch(info.get("target_id", ""))),
            "PERFORM_WATCH_BENEFIT": lambda: self.flow.perform_watch_benefit(info.get("target_id", ""), _choose_perform_benefit(info.get("target_id", ""))),
            "GIFT_NEED_TARGET": lambda: self.flow.gift_choose_target(_pick_target_low_progress(info.get("targets", [])) or ""),
            "EXCHANGE_NEED_TARGET": lambda: self.flow.exchange_choose_target(_pick_target_orange_rich(info.get("targets", [])) or ""),
            "EXCHANGE_NEED_CHOICE": _exchange_choose,
            "EXCHANGE_NEED_CONSENT": lambda: self.flow.exchange_consent(_decide_exchange_consent(info.get("target_id", ""))),
            "EVENT_NEED_TARGET": lambda: self.flow.event_choose_target(_pick_target_low_progress(info.get("targets", [])) or ""),
            "WATCH_DECIDE": lambda: self.flow.watch_decide(info.get("target_id", ""), _decide_watch_list(info.get("target_id", ""))),
            "TRADE_NEED_ITEM": lambda: self.flow.trade_choose_item(_choose_trade_item_index(info.get("items", []), info.get("role_id", "")) or 0),
            "TRADE_NEED_PARTNER": lambda: self.flow.trade_choose_partner(_pick_trade_partner(info.get("partners", [])) or ""),
            "TRADE_NEED_CONSENT": lambda: self.flow.trade_consent(_decide_trade_consent(info.get("partner_id", info.get("target_id", "")))),
        }

        if ui_mode in actions:
            return actions[ui_mode]()

        # ---------------------------
        # 抽卡：OR 代价选择（need_choice）
        # 说明：你现在 UI 里在 cost choice 阶段还有“取消/跳过”按钮
        # 我们这里也加入一个“取消”选项，概率均分
        # ---------------------------
        if ui_mode == "DRAW_NEED_COST_CHOICE":
            choices = info.get("choices", [])
            idx = _choose_draw_cost_index(choices, info.get("role_id", ""))
            if idx is None:
                return self.flow.end_turn()
            return self.flow.choose_draw_cost(idx)[1]  # ("next_turn", info)

        # ---------------------------
        # 默认：回合三选一（抽卡 / 技能 / 跳过）
        # ---------------------------
        can_draw = bool(info.get("can_draw", False))
        # 有些角色可能没有技能；你如果在 info 里叫 can_use_skill/can_use_skill，都可以兼容
        can_skill = bool(info.get("can_use_skill", info.get("has_skill", True)))

        if can_draw:
            kind, payload = self.flow.request_draw()
            if kind == "next_turn":
                return payload
            if kind == "need_choice":
                # 进入 cost-choice UI 模式（我们用 info 来表达）
                return {
                    "role_id": payload.get("role_id", ""),
                    "role_name": info.get("role_name", ""),
                    "ui_mode": "DRAW_NEED_COST_CHOICE",
                    "choices": payload.get("choices", []),
                }
            # fallback
            return self.flow.end_turn()

        if can_skill:
            return self.flow.use_active_skill()

        # SKIP
        return self.flow.end_turn()
