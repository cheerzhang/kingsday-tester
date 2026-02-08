import tkinter as tk
from tkinter import ttk, messagebox
from game_flow import GameFlow

from game_logic import (
    load_all_roles_min,
    init_game_runtime,
    load_current_game,
    load_player_gamestate,
    reset_runtime,
    REQUIRED_ROLE_IDS
)

RESOURCE_LABELS = {
    "stamina": "体力",
    "curiosity": "好奇心",
    "money": "金钱",
}

class SetupTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        # ----- state -----
        self.roles = []          # loaded from roles folder
        self.vars = {}           # role_id -> BooleanVar
        self.locked = False
        self.role_use_mode = None  

        # ----- header -----
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Setup (Tab3)", font=("Arial", 14, "bold")).pack(side="left")
        self.btn_reset = ttk.Button(head, text="Reset Game", command=self.reset_game)
        self.btn_reset.pack(side="right", padx=(0, 10))

        self.btn_start = ttk.Button(head, text="Start Game", command=self.start_game)
        self.btn_start.pack(side="right")

        # ----- roles list -----
        box = ttk.LabelFrame(self, text="Players (Finn + Tourist required)", padding=10)
        box.pack(fill="x", pady=(12, 10))
        self.roles_box = box

        # ----- mid layout: status (left) + current card (right) -----
        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True)

        # ----- status table (left) -----
        table_box = ttk.LabelFrame(mid, text="Game Status", padding=10)
        table_box.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.table = ttk.Treeview(table_box, columns=("role", "status"), show="headings", height=10)
        self.table.heading("role", text="Role")
        self.table.heading("status", text="status (from runtime gamestate)")
        self.table.column("role", width=200, anchor="w")
        self.table.column("status", width=800, anchor="w")
        self.table.pack(fill="both", expand=True)

        # ----- current card (right) -----
        card_box = ttk.LabelFrame(mid, text="Current Card", padding=10)
        card_box.pack(side="right", fill="y")

        self.card_id_var = tk.StringVar(value="None")
        self.card_name_var = tk.StringVar(value="None")
        self.card_label_var = tk.StringVar(value="None")
        self.role_effect_label_var = tk.StringVar(value="None")

        ttk.Label(card_box, text="Card ID:", font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(card_box, textvariable=self.card_id_var).pack(anchor="w", pady=(0, 8))
        ttk.Label(card_box, text="Card Name:", font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(card_box, textvariable=self.card_name_var).pack(anchor="w", pady=(0, 8))
        ttk.Label(card_box, text="Global Effect:", font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(card_box, textvariable=self.card_label_var, wraplength=260).pack(anchor="w")
        ttk.Label(card_box, text="Role Effect:", font=("Arial", 11, "bold")).pack(anchor="w", pady=(8, 0))
        ttk.Label(card_box, textvariable=self.role_effect_label_var, wraplength=260).pack(anchor="w")

        # ----- current turn panel -----
        turn_box = ttk.LabelFrame(self, text="Current Player", padding=10)
        turn_box.pack(fill="x", pady=(10, 0))

        self.turn_title_var = tk.StringVar(value="(not started)")
        ttk.Label(turn_box, textvariable=self.turn_title_var, font=("Arial", 13, "bold")).pack(anchor="w")

        self.turn_detail_var = tk.StringVar(value="")
        ttk.Label(turn_box, textvariable=self.turn_detail_var, foreground="#bbb").pack(anchor="w", pady=(6, 0))

        # ----- action buttons (turn actions) -----
        self.action_bar = ttk.Frame(self)
        self.action_bar.pack(fill="x", pady=(10, 0))

        self.btn_draw = ttk.Button(self.action_bar, text="抽卡", command=self.on_draw)
        self.btn_role_use = ttk.Button(self.action_bar, text="使用个人效果 (-1体力)", command=self.on_role_use)
        self.btn_nodraw = ttk.Button(self.action_bar, text="跳过", command=self.on_no_draw)
        self.btn_role_skip = ttk.Button(self.action_bar, text="不使用", command=self.on_role_skip)
        self.cost_buttons = []
        self.show_turn_actions(False)  # start with only "不抽卡" or hide all (取决于你的实现)
        
        # ----- log -----
        log_box = ttk.LabelFrame(self, text="Log", padding=10)
        log_box.pack(fill="both", expand=True, pady=(10, 0))

        self.log_text = tk.Text(log_box, height=10, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        # ----- footer -----
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, foreground="#666").pack(anchor="w", pady=(10, 0))

        self.refresh_roles()

    # ======================
    # UI building
    # ======================
    def refresh_roles(self):
        for w in self.roles_box.winfo_children():
            w.destroy()
        self.vars = {}
        self.roles = load_all_roles_min()
        self.vars.clear()
        self.locked = False
        self.btn_start.configure(state="normal")

        if not self.roles:
            ttk.Label(self.roles_box, text="No roles found in data/roles").pack(anchor="w")
            return

        # build checkboxes (show name only)
        for r in self.roles:
            rid = r["id"]
            name = r["name"]

            v = tk.BooleanVar(value=(rid in REQUIRED_ROLE_IDS))
            self.vars[rid] = v

            cb = ttk.Checkbutton(self.roles_box, text=name, variable=v)
            cb.pack(anchor="w", pady=2)

            # required roles: cannot uncheck
            if rid in REQUIRED_ROLE_IDS:
                cb.configure(state="disabled")

        self.status.set("Select players, then Start Game.")

    # ======================
    # Start game
    # ======================
    def start_game(self):
        if self.locked:
            return

        chosen = [rid for rid, v in self.vars.items() if v.get()]

        # enforce required on UI side too
        for req in REQUIRED_ROLE_IDS:
            if req not in chosen:
                chosen.append(req)

        if len(chosen) < 2:
            messagebox.showerror("Start Game", "Need at least Finn + Tourist.")
            return

        players = init_game_runtime(chosen)

        # start game flow (turn 1 + can_draw)
        self.flow = GameFlow()
        info = self.flow.start_game()

        # lock UI (cannot change after start)
        self.locked = True
        self.btn_start.configure(state="disabled")
        for child in self.roles_box.winfo_children():
            try:
                child.configure(state="disabled")
            except Exception:
                pass

        self.status.set("Game started. Runtime files generated.")
        self.render_status(players)
        
        # logs + enter first turn
        self.append_flow_logs()

        if not info:
            messagebox.showerror("Start Game", "GameFlow failed to start.")
            return

        self.enter_turn(info)

    # ======================
    # Show runtime status
    # ======================
    def render_status(self, players: list[str] | None = None):
        for i in self.table.get_children():
            self.table.delete(i)

        cur = load_current_game()
        players = players or cur.get("players", [])

        # show status per player
        for rid in players:
            gs = load_player_gamestate(rid)
            st = gs.get("status", {})
            if not isinstance(st, dict):
                st = {}

            # compact string (show keys sorted)
            keys = sorted(st.keys())
            status_str = ", ".join([f"{k}={st.get(k,0)}" for k in keys])

            # show name (from roles list) if possible
            name = rid
            for r in self.roles:
                if r["id"] == rid:
                    name = r["name"]
                    break

            self.table.insert("", "end", values=(name, status_str))
    
    # ======================
    # Reset game
    # ======================
    def reset_game(self):
        if not messagebox.askyesno("Reset Game", "Delete all runtime files and clear UI?"):
            return
        reset_runtime()
        self.flow = None
        try:
            self.clear_action_buttons()
        except Exception:
            pass
        self.locked = False
        self.btn_start.configure(state="normal")
        try:
            for w in self.roles_box.winfo_children():
                w.destroy()
        except Exception:
            pass
        self.vars = {}
        self.roles = []
        for i in self.table.get_children():
            self.table.delete(i)
        self.turn_title_var.set("(not started)")
        self.turn_detail_var.set("")
        self.card_id_var.set("None")
        self.card_name_var.set("None")
        self.card_label_var.set("None")
        self.role_effect_label_var.set("None")
        try:
            self.log_text.delete("1.0", "end")
        except Exception:
            pass
        self.refresh_roles()
        self.status.set("Runtime cleared. Ready.")


    def append_flow_logs(self):
        if not hasattr(self, "flow") or not self.flow:
            return
        for line in self.flow.consume_logs():
            self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
    
    def show_turn_actions(self, can_draw: bool):
        # 你需要一个容器 self.action_bar
        for w in self.action_bar.winfo_children():
            w.pack_forget()

        if can_draw:
            self.btn_draw.pack(side="left", padx=6)

        self.btn_nodraw.pack(side="left", padx=6)
    
    # ======================
    # Enter game info: {"role_id":..., "role_name":..., "can_draw":...}
    # ======================
    def enter_turn(self, info: dict):
        self.role_use_mode = None
        self.clear_action_buttons()
        if not isinstance(info, dict):
            return
        ui_mode = info.get("ui_mode", "")

        rid = info.get("role_id", "")
        name = info.get("role_name", rid)
        # 1) 当前玩家信息
        self.turn_title_var.set(f"Turn: {name} ({rid})")
        gs = load_player_gamestate(rid)
        st = gs.get("status", {})
        if not isinstance(st, dict):
            st = {}
        detail = ", ".join([f"{k}={st.get(k,0)}" for k in sorted(st.keys())])
        self.turn_detail_var.set(detail)

        # update current card display (show until turn ends)
        ce = getattr(self.flow, "current_event_info", None)
        if isinstance(ce, dict):
            self.card_id_var.set(ce.get("id") or "None")
            self.card_name_var.set(ce.get("name") or "None")
            lab = ce.get("global_label") or "None"
            self.card_label_var.set(lab)
            self.role_effect_label_var.set(ce.get("role_label") or "None")
        else:
            self.card_id_var.set("None")
            self.card_name_var.set("None")
            self.card_label_var.set("None")
            self.role_effect_label_var.set("None")
        # =========================================================
        # 2) 显示按钮（这里就是你要找的“显示按钮的那部分”）
        #    - 互动流程（拍照/交易）优先显示对应按钮
        #    - 抽卡后个人效果选择：显示 使用/不使用
        #    - 否则：回合三选一：抽卡 / 发动技能 / 跳过
        # =========================================================
        # 2.1 互动流程：交易
        if ui_mode == "TRADE_NEED_ITEM":
            self.show_trade_items(info.get("items", []))

        elif ui_mode == "TRADE_NEED_PARTNER":
            self.show_trade_partners(info.get("partners", []))

        elif ui_mode == "TRADE_NEED_CONSENT":
            self.show_trade_consent(info.get("partner_id", ""))
        # 2.2 互动流程：拍照
        elif ui_mode == "PHOTO_NEED_TARGET":
            self.show_photo_targets(info.get("targets", []))
        elif ui_mode == "WEAR_NEED_TARGET":
            self.show_wear_targets(info.get("targets", []))

        elif ui_mode == "PHOTO_NEED_CONSENT":
            self.show_photo_consent(info.get("target_id", ""))
        elif ui_mode == "FOOD_OFFER_DECIDE":
            self.show_food_offer_decide(info.get("target_id", ""), info.get("price", 0))
        elif ui_mode == "FOOD_OFFER_FORCE":
            self.show_food_offer_force(info.get("target_id", ""), info.get("price", 0))
        elif ui_mode == "PERFORM_WATCH_DECIDE":
            self.show_perform_watch_decide(info.get("target_id", ""))
        elif ui_mode == "PERFORM_WATCH_BENEFIT":
            self.show_perform_watch_benefit(info.get("target_id", ""))
        elif ui_mode == "GIFT_NEED_TARGET":
            self.show_gift_targets(info.get("targets", []))
        elif ui_mode == "EXCHANGE_NEED_TARGET":
            self.show_exchange_targets(info.get("targets", []))
        elif ui_mode == "EXCHANGE_NEED_CHOICE":
            self.show_exchange_choices(info.get("options", []))
        elif ui_mode == "EXCHANGE_NEED_CONSENT":
            self.show_exchange_consent(info.get("target_id", ""))
        elif ui_mode == "EVENT_NEED_TARGET":
            self.show_event_targets(info.get("targets", []))
        elif ui_mode == "WATCH_DECIDE":
            self.show_watch_decide(info.get("target_id", ""))
        elif ui_mode == "HELP_DECISION":
            self.show_help_decision(info.get("help_action", ""))
        # 2.3 抽卡后：个人效果选择（使用 / 不使用）
        elif info.get("post_role_effect_choice"):
            self.role_use_mode = "CARD_EFFECT"
            can_trigger = bool(info.get("can_trigger", False))
            self.btn_role_use.configure(state=("normal" if can_trigger else "disabled"))
            self.btn_role_use.configure(text="使用个人效果 (-1体力)")
            self.btn_role_use.pack(side="left", padx=6)
            self.btn_role_skip.configure(text="不使用", state="normal")
            self.btn_role_skip.pack(side="left", padx=6)
        # 2.5 默认：回合三选一（抽卡 / 发动技能 / 跳过）
        else:
            self.role_use_mode = "ACTIVE_SKILL"
            can_draw = bool(info.get("can_draw", False))
            has_skill = bool(info.get("has_skill", True))  # 没给就默认有技能（方便你先跑通）
            # 抽卡
            if can_draw:
                self.btn_draw.pack(side="left", padx=6)
            # 发动技能（固定走 on_role_use -> flow.use_active_skill）
            self.btn_role_use.configure(text="发动技能", state=("normal" if has_skill else "disabled"))
            self.btn_role_use.pack(side="left", padx=6)
            # 跳过（固定走 on_no_draw -> flow.end_turn）
            self.btn_nodraw.configure(text="跳过", state="normal")
            self.btn_nodraw.pack(side="left", padx=6)
        # 3) 刷新状态表（所有人状态可能会变）
        cur = load_current_game()
        players = cur.get("players", [])
        if not isinstance(players, list):
            players = []
        self.render_status(players)

        # 4) 打印 flow log
        self.append_flow_logs()


    ########################
    #  选不抽卡的逻辑
    ##########################
    def on_no_draw(self):
        if not hasattr(self, "flow") or not self.flow:
            return
        self.flow.request_no_draw_choice()
        self.append_flow_logs()
        info = self.flow.skip_turn()
        self.append_flow_logs()
        self.enter_turn(info)


    def on_draw(self):
        self.clear_action_buttons()
        if not hasattr(self, "flow") or not self.flow:
            return

        kind, payload = self.flow.request_draw()
        self.append_flow_logs()

        if kind == "need_choice":
            # stay on same player, show OR choices
            self.show_cost_choice(payload.get("choices", []))
            return

        # next_turn
        self.enter_turn(payload)
    
    def on_choose_cost(self, i: int):
        self.clear_action_buttons() 
        kind, payload = self.flow.choose_draw_cost(i)
        self.append_flow_logs()
        self.enter_turn(payload)

    def show_cost_choice(self, choices: list[dict]):
        self.clear_action_buttons()
        self.cost_buttons = []
        for idx, opt in enumerate(choices):
            costs = opt.get("costs")
            if isinstance(costs, list) and costs:
                parts = []
                for c in costs:
                    res = str(c.get("resource", ""))
                    delta = int(c.get("delta", 0))
                    lab = RESOURCE_LABELS.get(res, res)
                    parts.append(f"{lab} {delta}")
                text = "支付 " + " + ".join(parts)
            else:
                res = str(opt.get("resource", ""))
                delta = int(opt.get("delta", 0))
                lab = RESOURCE_LABELS.get(res, res)
                text = f"支付 {lab} {delta}"  # delta=-1 就显示 -1
            btn = ttk.Button(
                self.action_bar,
                text=text,
                command=lambda i=idx: self.on_choose_cost(i)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)
        self.btn_nodraw.pack(side="left", padx=6)
    

    #####################
    # show btn
    ####################
    def show_turn_actions(self, can_draw: bool):
        for w in self.action_bar.winfo_children():
            w.pack_forget()

        if can_draw:
            self.btn_draw.pack(side="left", padx=6)

        self.btn_nodraw.pack(side="left", padx=6)
    

    def on_role_use(self):
        self.clear_action_buttons()
        if not self.flow:
            return

        if self.role_use_mode == "ACTIVE_SKILL":
            info = self.flow.use_active_skill()

        elif self.role_use_mode == "CARD_EFFECT":
            info = self.flow.trigger_role_effect()

        else:
            # 防御性：什么都不做
            info = self.flow.end_turn()

        self.append_flow_logs()
        self.render_status(self.flow.players)
        self.enter_turn(info)

 
    def on_role_skip(self):
        self.clear_action_buttons()
        if not hasattr(self, "flow") or not self.flow:
            return
        mode = getattr(self, "ui_mode", "")
        if mode == "NO_DRAW_CHOICE":
            info = self.flow.skip_turn()     
        else:
            info = self.flow.skip_role_effect()
        self.append_flow_logs()
        self.render_status(self.flow.players)
        self.enter_turn(info)
    

    #####################
    # clear btn
    ####################
    def clear_action_buttons(self):
        # 固定按钮：只隐藏
        for btn in (
            self.btn_draw,
            self.btn_nodraw,
            self.btn_role_use,
            self.btn_role_skip,
        ):
            try:
                btn.pack_forget()
            except Exception:
                pass

        # ✅ 动态代价按钮：必须 destroy
        for w in getattr(self, "cost_buttons", []):
            try:
                w.destroy()
            except Exception:
                pass

        self.cost_buttons = []


    #####################
    # take photo btn
    ####################
    def get_role_name(self, role_id: str) -> str:
        for r in self.roles:
            if r.get("id") == role_id:
                return r.get("name", role_id)
        return role_id

    def on_photo_target(self, target_id: str):
        # 进入下一阶段前，先清按钮
        self.clear_action_buttons()

        info = self.flow.photo_choose_target(target_id)
        self.enter_turn(info)

    def on_photo_agree(self, agree: bool):
        self.clear_action_buttons()

        info = self.flow.photo_consent(agree)
        self.enter_turn(info)

    def show_photo_targets(self, targets: list[str]):
        self.clear_action_buttons()

        if not isinstance(targets, list):
            targets = []

        # 动态按钮列表（方便 destroy）
        self.cost_buttons = []

        # 目标按钮
        for rid in targets:
            # 显示名字更友好
            try:
                name = self.get_role_name(rid)
            except Exception:
                name = rid

            btn = ttk.Button(
                self.action_bar,
                text=f"拍 {name}",
                command=lambda x=rid: self.on_photo_target(x)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

        # 允许跳过（这里用“不使用”按钮更统一）
        self.btn_role_skip.configure(text="跳过拍照")
        self.btn_role_skip.pack(side="left", padx=6)

    def show_wear_targets(self, targets: list[str]):
        self.clear_action_buttons()

        if not isinstance(targets, list):
            targets = []

        # 动态按钮列表（方便 destroy）
        self.cost_buttons = []

        for rid in targets:
            try:
                name = self.get_role_name(rid)
            except Exception:
                name = rid
            btn = ttk.Button(
                self.action_bar,
                text=f"给 {name} 穿上",
                command=lambda x=rid: self.on_photo_target(x)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

        self.btn_role_skip.configure(text="跳过")
        self.btn_role_skip.pack(side="left", padx=6)


    def show_photo_consent(self, target_id: str):
        """
        显示：对方同意 / 拒绝
        """
        self.clear_action_buttons()

        try:
            target_name = self.get_role_name(rid)
        except Exception:
            target_name = target_id

        self.cost_buttons = []

        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{target_name}：同意",
            command=lambda: self.on_photo_agree(True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)

        btn_no = ttk.Button(
            self.action_bar,
            text=f"{target_name}：拒绝",
            command=lambda: self.on_photo_agree(False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)
    

    #####################
    # Trade btn
    ####################
    def show_trade_items(self, items: list[dict]):
        self.clear_action_buttons()
        if not isinstance(items, list):
            items = []
        self.cost_buttons = []
        for idx, it in enumerate(items):
            label = str(it.get("label") or it.get("kind") or f"item{idx}")
            btn = ttk.Button(
                self.action_bar,
                text=f"交易物品：{label}",
                command=lambda i=idx: self.on_trade_item(i)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)
        # 允许跳过交易（等价于不使用个人效果）
        self.btn_role_skip.configure(text="跳过交易")
        self.btn_role_skip.pack(side="left", padx=6)
    
    def show_trade_partners(self, partners: list[str]):
        self.clear_action_buttons()
        if not isinstance(partners, list):
            partners = []
        self.cost_buttons = []
        for rid in partners:
            name = self.get_role_name(rid)
            btn = ttk.Button(
                self.action_bar,
                text=f"交易对象：{name}",
                command=lambda x=rid: self.on_trade_partner(x)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)
        self.btn_role_skip.configure(text="取消交易")
        self.btn_role_skip.pack(side="left", padx=6)
    
    def show_trade_consent(self, partner_id: str):
        self.clear_action_buttons()
        partner_name = self.get_role_name(partner_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{partner_name}：同意交易",
            command=lambda: self.on_trade_agree(True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text=f"{partner_name}：拒绝交易",
            command=lambda: self.on_trade_agree(False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)
        self.btn_role_skip.configure(text="取消")
        self.btn_role_skip.pack(side="left", padx=6)

    def show_help_decision(self, action_type: str):
        self.clear_action_buttons()
        label = action_type or "action"
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"志愿者帮助（{label}）",
            command=lambda: self.on_help(True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text="不帮助",
            command=lambda: self.on_help(False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)

    def on_help(self, agree: bool):
        if not self.flow:
            return
        try:
            info = self.flow.volunteer_help(agree)
        except Exception as e:
            messagebox.showerror("Help", f"volunteer_help failed:\n{e}")
            return
        self.enter_turn(info)

    def show_food_offer_decide(self, target_id: str, price: int):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{name}：接受供餐 (-{price}金钱)",
            command=lambda: self.on_food_offer(target_id, True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text=f"{name}：不接受",
            command=lambda: self.on_food_offer(target_id, False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)

    def on_food_offer(self, target_id: str, accept: bool):
        if not self.flow:
            return
        try:
            info = self.flow.food_offer_decide(target_id, accept)
        except Exception as e:
            messagebox.showerror("Food Offer", f"food_offer_decide failed:\n{e}")
            return
        self.enter_turn(info)

    def show_food_offer_force(self, target_id: str, price: int):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{name}：必须接受供餐 (-{price}金钱)",
            command=lambda: self.on_food_offer(target_id, True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)

    def show_perform_watch_decide(self, target_id: str):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{name}：围观",
            command=lambda: self.on_perform_watch_decide(target_id, True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text=f"{name}：不围观",
            command=lambda: self.on_perform_watch_decide(target_id, False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)

    def on_perform_watch_decide(self, target_id: str, watch: bool):
        if not self.flow:
            return
        try:
            info = self.flow.perform_watch_decide(target_id, watch)
        except Exception as e:
            messagebox.showerror("Perform", f"perform_watch_decide failed:\n{e}")
            return
        self.enter_turn(info)

    def show_perform_watch_benefit(self, target_id: str):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_a = ttk.Button(
            self.action_bar,
            text=f"{name}：体力+1 好奇-1",
            command=lambda: self.on_perform_watch_benefit(target_id, "stamina_plus_curiosity_minus")
        )
        btn_a.pack(side="left", padx=6)
        self.cost_buttons.append(btn_a)
        btn_b = ttk.Button(
            self.action_bar,
            text=f"{name}：金钱-1 好奇+1",
            command=lambda: self.on_perform_watch_benefit(target_id, "money_minus_curiosity_plus")
        )
        btn_b.pack(side="left", padx=6)
        self.cost_buttons.append(btn_b)

    def on_perform_watch_benefit(self, target_id: str, choice: str):
        if not self.flow:
            return
        try:
            info = self.flow.perform_watch_benefit(target_id, choice)
        except Exception as e:
            messagebox.showerror("Perform", f"perform_watch_benefit failed:\n{e}")
            return
        self.enter_turn(info)

    def show_gift_targets(self, targets: list[str]):
        self.clear_action_buttons()
        self.cost_buttons = []
        for rid in targets:
            name = self.get_role_name(rid)
            btn = ttk.Button(
                self.action_bar,
                text=f"送给 {name}",
                command=lambda r=rid: self.on_gift_target(r)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

    def on_gift_target(self, target_id: str):
        if not self.flow:
            return
        try:
            info = self.flow.gift_choose_target(target_id)
        except Exception as e:
            messagebox.showerror("Gift", f"gift_choose_target failed:\n{e}")
            return
        self.enter_turn(info)

    def show_exchange_targets(self, targets: list[str]):
        self.clear_action_buttons()
        self.cost_buttons = []
        for rid in targets:
            name = self.get_role_name(rid)
            btn = ttk.Button(
                self.action_bar,
                text=f"与 {name} 交换",
                command=lambda r=rid: self.on_exchange_target(r)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

    def on_exchange_target(self, target_id: str):
        if not self.flow:
            return
        try:
            info = self.flow.exchange_choose_target(target_id)
        except Exception as e:
            messagebox.showerror("Exchange", f"exchange_choose_target failed:\n{e}")
            return
        self.enter_turn(info)

    def show_exchange_choices(self, options: list[dict]):
        self.clear_action_buttons()
        self.cost_buttons = []
        for idx, opt in enumerate(options):
            label = str(opt.get("label", f"选项{idx+1}"))
            btn = ttk.Button(
                self.action_bar,
                text=label,
                command=lambda i=idx: self.on_exchange_choice(i)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

    def on_exchange_choice(self, option_index: int):
        if not self.flow:
            return
        try:
            info = self.flow.exchange_choose_option(option_index)
        except Exception as e:
            messagebox.showerror("Exchange", f"exchange_choose_option failed:\n{e}")
            return
        self.enter_turn(info)

    def show_exchange_consent(self, target_id: str):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{name}：同意交换",
            command=lambda: self.on_exchange_consent(True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text=f"{name}：拒绝交换",
            command=lambda: self.on_exchange_consent(False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)

    def on_exchange_consent(self, agree: bool):
        if not self.flow:
            return
        try:
            info = self.flow.exchange_consent(agree)
        except Exception as e:
            messagebox.showerror("Exchange", f"exchange_consent failed:\n{e}")
            return
        self.enter_turn(info)

    def show_event_targets(self, targets: list[str]):
        self.clear_action_buttons()
        self.cost_buttons = []
        for rid in targets:
            name = self.get_role_name(rid)
            btn = ttk.Button(
                self.action_bar,
                text=f"选择 {name}",
                command=lambda r=rid: self.on_event_target(r)
            )
            btn.pack(side="left", padx=6)
            self.cost_buttons.append(btn)

    def on_event_target(self, target_id: str):
        if not self.flow:
            return
        try:
            info = self.flow.event_choose_target(target_id)
        except Exception as e:
            messagebox.showerror("Event", f"event_choose_target failed:\n{e}")
            return
        self.enter_turn(info)

    def show_watch_decide(self, target_id: str):
        self.clear_action_buttons()
        name = self.get_role_name(target_id)
        self.cost_buttons = []
        btn_yes = ttk.Button(
            self.action_bar,
            text=f"{name}：围观",
            command=lambda: self.on_watch_decide(target_id, True)
        )
        btn_yes.pack(side="left", padx=6)
        self.cost_buttons.append(btn_yes)
        btn_no = ttk.Button(
            self.action_bar,
            text=f"{name}：不围观",
            command=lambda: self.on_watch_decide(target_id, False)
        )
        btn_no.pack(side="left", padx=6)
        self.cost_buttons.append(btn_no)

    def on_watch_decide(self, target_id: str, watch: bool):
        if not self.flow:
            return
        try:
            info = self.flow.watch_decide(target_id, watch)
        except Exception as e:
            messagebox.showerror("Event", f"watch_decide failed:\n{e}")
            return
        self.enter_turn(info)
    
    def on_trade_agree(self, agree: bool):
        """
        点击：对方同意/拒绝交易
        """
        if not self.flow:
            return
        try:
            info = self.flow.trade_consent(agree)
        except Exception as e:
            messagebox.showerror("Trade", f"trade_consent failed:\n{e}")
            return
        self.enter_turn(info)

    def on_trade_item(self, item_index: int):
        """
        点击：选择交易物品
        """
        if not self.flow:
            return
        try:
            info = self.flow.trade_choose_item(item_index)
        except Exception as e:
            messagebox.showerror("Trade", f"trade_choose_item failed:\n{e}")
            return
        self.enter_turn(info)
    
    def on_trade_partner(self, partner_id: str):
        """
        点击：选择交易对象
        """
        if not self.flow:
            return
        try:
            info = self.flow.trade_choose_partner(partner_id)
        except Exception as e:
            messagebox.showerror("Trade", f"trade_choose_partner failed:\n{e}")
            return
        self.enter_turn(info)
