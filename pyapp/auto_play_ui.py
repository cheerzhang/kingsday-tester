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
    reset_runtime,
)
from game_flow import GameFlow


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
        cur = load_current_game()
        if cur.get("game_over"):
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
        把“UI 按钮选择”改成随机选择（均匀概率）。
        只调用现有 flow 方法，不重写规则。
        """
        ui_mode = info.get("ui_mode", "")

        # ---------------------------
        # 互动：拍照
        # ---------------------------
        if ui_mode == "PHOTO_NEED_TARGET":
            targets = info.get("targets", [])
            if not targets:
                return self.flow.end_turn()
            target_id = random.choice(list(targets))
            return self.flow.photo_choose_target(target_id)

        if ui_mode == "PHOTO_NEED_CONSENT":
            agree = random.choice([True, False])
            return self.flow.photo_consent(agree)

        # ---------------------------
        # 互动：交易
        # ---------------------------
        if ui_mode == "TRADE_NEED_ITEM":
            items = info.get("items", [])
            if not items:
                return self.flow.end_turn()
            idx = random.randrange(len(items))
            return self.flow.trade_choose_item(idx)

        if ui_mode == "TRADE_NEED_PARTNER":
            partners = info.get("partners", [])
            if not partners:
                return self.flow.end_turn()
            partner_id = random.choice(list(partners))
            return self.flow.trade_choose_partner(partner_id)

        if ui_mode == "TRADE_NEED_CONSENT":
            agree = random.choice([True, False])
            return self.flow.trade_consent(agree)

        # ---------------------------
        # 抽卡：OR 代价选择（need_choice）
        # 说明：你现在 UI 里在 cost choice 阶段还有“取消/跳过”按钮
        # 我们这里也加入一个“取消”选项，概率均分
        # ---------------------------
        if ui_mode == "DRAW_NEED_COST_CHOICE":
            choices = info.get("choices", [])
            opts = []
            for i in range(len(choices)):
                opts.append(("pay", i))
            opts.append(("cancel", None))

            kind, payload = random.choice(opts)
            if kind == "cancel":
                return self.flow.end_turn()
            else:
                # i
                i = payload
                return self.flow.choose_draw_cost(i)[1]  # ("next_turn", info)

        # ---------------------------
        # 抽卡后：个人效果是否触发（使用 / 不使用）
        # ---------------------------
        if info.get("post_role_effect_choice"):
            # 两个按钮均分
            use_it = random.choice([True, False])
            if use_it:
                return self.flow.trigger_role_effect()
            else:
                return self.flow.skip_role_effect()

        # ---------------------------
        # 默认：回合三选一（抽卡 / 技能 / 跳过）
        # ---------------------------
        can_draw = bool(info.get("can_draw", False))
        # 有些角色可能没有技能；你如果在 info 里叫 can_use_skill/can_use_skill，都可以兼容
        can_skill = bool(info.get("can_use_skill", info.get("has_skill", True)))

        actions = []
        if can_draw:
            actions.append("DRAW")
        if can_skill:
            actions.append("SKILL")
        actions.append("SKIP")

        pick = random.choice(actions)

        if pick == "DRAW":
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

        if pick == "SKILL":
            return self.flow.use_active_skill()

        # SKIP
        return self.flow.end_turn()