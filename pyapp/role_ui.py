import json, os
import tkinter as tk
from tkinter import ttk, messagebox

# ======================
# Paths & IO
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLES_DIR = os.path.join(ROOT, "data", "roles")
GLOBAL_VICTORY_DEFS = os.path.join(ROOT, "data", "global_defs.json")

def list_role_files():
    if not os.path.isdir(ROLES_DIR):
        return []
    return sorted(f for f in os.listdir(ROLES_DIR) if f.endswith(".json"))

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def to_int_min0(v):
    try:
        v = int(v)
    except Exception:
        v = 0
    return max(0, v)

# ======================
# Victory defs (read-only global)
# ======================
def load_victory_defs():
    """
    Reads data/global_victory_defs.json
    Returns:
      defs_map: { id: {label_template:str, param_defaults:{...}} }
      ids: [id1, id2, ...] in file order
    """
    try:
        with open(GLOBAL_VICTORY_DEFS, "r", encoding="utf-8") as f:
            obj = json.load(f)
        arr = obj.get("victory_defs", [])
        if not isinstance(arr, list):
            return {}, []
        ids = []
        mp = {}
        for it in arr:
            if not isinstance(it, dict):
                continue
            vid = it.get("id")
            if not vid:
                continue
            ids.append(vid)
            mp[vid] = {
                "label_template": it.get("label_template", vid),
                "param_defaults": it.get("param_defaults", {"n": 0})
            }
        return mp, ids
    except Exception:
        return {}, []

# ======================
# Draw cost config (UI constants)
# ======================
DRAW_RESOURCES = [
    ("stamina", "体力"),
    ("curiosity", "好奇"),
    ("money", "金钱"),
]
DRAW_LOGICS = ["THEN", "OR"]

# ======================
# Role Tab
# ======================
class RoleTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        # ----- state -----
        self.role = None
        self.role_path = None
        self.value_vars = {}   # key -> StringVar
        self.victory_defs, self.victory_ids = load_victory_defs()  # victory defs (global read-only)

        # ----- header -----
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Role (Tab1)", font=("Arial", 14, "bold")).pack(side="left")
        ttk.Button(head, text="Save the change", command=self.save).pack(side="right")

        # ----- selector -----
        sel = ttk.Frame(self)
        sel.pack(fill="x", pady=(12, 10))
        ttk.Label(sel, text="Role file:").pack(side="left")

        self.combo_var = tk.StringVar()
        self.combo = ttk.Combobox(sel, textvariable=self.combo_var, state="readonly", width=40)
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<Button-1>", lambda e: self.combo.focus_set())
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.load_selected())

        # ----- basic info -----
        info = ttk.LabelFrame(self, text="Basic (read-only)", padding=10)
        info.pack(fill="x")

        self.name_var = tk.StringVar(value="-")
        self.id_var = tk.StringVar(value="-")

        self._row(info, "name:", self.name_var)
        self._row(info, "id:", self.id_var)

        # ----- init_number editor -----
        self.init_box = ttk.LabelFrame(self, text="Initial Numbers", padding=10)
        self.init_box.pack(fill="x", pady=(10, 0))
        self.init_line = ttk.Frame(self.init_box)
        self.init_line.pack(fill="x")

        # ----- victory editor -----
        self.victory_box = ttk.LabelFrame(self, text="Victory", padding=10)
        self.victory_box.pack(fill="x", pady=(10, 0))

        self.victory_id_var = tk.StringVar(value="")
        self.victory_n_var = tk.StringVar(value="0")
        self.victory_preview_var = tk.StringVar(value="(not set)")

        vrow = ttk.Frame(self.victory_box)
        vrow.pack(fill="x")

        ttk.Label(vrow, text="condition:", width=12).pack(side="left")
        self.victory_combo = ttk.Combobox(
            vrow,
            textvariable=self.victory_id_var,
            values=self.victory_ids,
            state="readonly",
            width=22
        )
        self.victory_combo.pack(side="left", padx=(0, 12))

        ttk.Label(vrow, text="N:", width=2).pack(side="left")
        self.victory_spin = ttk.Spinbox(vrow, from_=0, to=999, textvariable=self.victory_n_var, width=6)
        self.victory_spin.pack(side="left", padx=(6, 12))
        self.victory_preview_label = ttk.Label(
            vrow,
            textvariable=self.victory_preview_var,
            foreground="#bbb",     # 深色背景更显眼（你也可以用 #ddd）
            width=30               # ✅ 给个最小宽度，防止被挤成 0
            )
        self.victory_preview_label.pack(side="left", padx=(12, 0))

        # update preview when changed
        self.victory_id_var.trace_add("write", lambda *_: self._update_victory_preview())
        self.victory_n_var.trace_add("write", lambda *_: self._update_victory_preview())

        # ----- draw card cost editor -----
        self.cost_box = ttk.LabelFrame(self, text="Draw Card Cost (max 2)", padding=10)
        self.cost_box.pack(fill="x", pady=(10, 0))

        self.cost_logic_var = tk.StringVar(value="THEN")

        # slot A
        self.cost_a_enabled = tk.BooleanVar(value=True)
        self.cost_a_res = tk.StringVar(value="stamina")
        self.cost_a_amt = tk.StringVar(value="1")

        # slot B
        self.cost_b_enabled = tk.BooleanVar(value=False)
        self.cost_b_res = tk.StringVar(value="curiosity")
        self.cost_b_amt = tk.StringVar(value="1")

        self._build_draw_cost_ui()

        # ----- status -----
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, foreground="#666").pack(anchor="w", pady=(10, 0))

        # init list
        self.refresh_list(select_first=True)

    # ------------------
    # small helpers
    # ------------------
    def _row(self, parent, label, var):
        r = ttk.Frame(parent)
        r.pack(fill="x", pady=2)
        ttk.Label(r, text=label, width=10).pack(side="left")
        ttk.Label(r, textvariable=var).pack(side="left")

    def _clear_init_line(self):
        for w in self.init_line.winfo_children():
            w.destroy()
        self.value_vars.clear()
    
        # ==================
    # Draw cost UI
    # ==================
    def _build_draw_cost_ui(self):
        wrap = ttk.Frame(self.cost_box)
        wrap.pack(fill="x")

        # row: slot A + slot B + logic
        self._cost_row(wrap, "A", self.cost_a_enabled, self.cost_a_res, self.cost_a_amt)
        self._cost_row(wrap, "B", self.cost_b_enabled, self.cost_b_res, self.cost_b_amt)

        logic_row = ttk.Frame(self.cost_box)
        logic_row.pack(fill="x", pady=(8, 0))

        ttk.Label(logic_row, text="logic (when 2):", width=14).pack(side="left")
        self.logic_combo = ttk.Combobox(logic_row, textvariable=self.cost_logic_var,
                                        values=DRAW_LOGICS, state="readonly", width=8)
        self.logic_combo.pack(side="left")

        # keep logic enabled only when B is enabled
        def _sync_logic(*_):
            self.logic_combo.configure(state="readonly" if self.cost_b_enabled.get() else "disabled")
        self.cost_b_enabled.trace_add("write", _sync_logic)
        _sync_logic()

    def _cost_row(self, parent, tag, enabled_var, res_var, amt_var):
        row = ttk.Frame(parent)
        row.pack(side="left", padx=(0, 20))

        ttk.Checkbutton(row, text=f"Slot {tag}", variable=enabled_var).pack(side="left", padx=(0, 8))

        res_combo = ttk.Combobox(
            row, textvariable=res_var,
            values=[k for (k, _lab) in DRAW_RESOURCES],
            state="readonly", width=10
        )
        res_combo.pack(side="left", padx=(0, 6))

        ttk.Label(row, text="-").pack(side="left")
        sp = ttk.Spinbox(row, from_=0, to=999, textvariable=amt_var, width=5)
        sp.pack(side="left", padx=(6, 0))

    def _load_draw_cost_from_role(self, role):
        dc = role.get("draw_card_cost")
        if not isinstance(dc, dict):
            # JSON没有配置 => UI显示未启用（不填默认）
            self.cost_a_enabled.set(False)
            self.cost_b_enabled.set(False)
            self.cost_logic_var.set("THEN")  # 只是占位，逻辑会被禁用
            self.status.set("Loaded (draw_card_cost: NOT SET)")
            return

        logic = str(dc.get("logic", "")).upper()
        if logic not in ("THEN", "OR"):
            logic = "THEN"
        self.cost_logic_var.set(logic)

        opts = dc.get("options")
        if not isinstance(opts, list):
            opts = []

        # slot A
        if len(opts) >= 1 and isinstance(opts[0], dict):
            self.cost_a_enabled.set(True)
            self.cost_a_res.set(str(opts[0].get("resource", "")))
            self.cost_a_amt.set(str(abs(int(opts[0].get("delta", -1))) if str(opts[0].get("delta", -1)).lstrip("-").isdigit() else 1))
        else:
            self.cost_a_enabled.set(False)

        # slot B
        if len(opts) >= 2 and isinstance(opts[1], dict):
            self.cost_b_enabled.set(True)
            self.cost_b_res.set(str(opts[1].get("resource", "")))
            self.cost_b_amt.set(str(abs(int(opts[1].get("delta", -1))) if str(opts[1].get("delta", -1)).lstrip("-").isdigit() else 1))
        else:
            self.cost_b_enabled.set(False)

    # ------------------
    # load role
    # ------------------
    def refresh_list(self, select_first=False):
        files = list_role_files()
        self.combo["values"] = files
        if files and select_first:
            self.combo.current(0)
            self.load_selected()

    def load_selected(self):
        fn = self.combo_var.get()
        if not fn:
            return

        path = os.path.join(ROLES_DIR, fn)
        try:
            role = load_json(path)

            self.role = role
            self.role_path = path

            self.name_var.set(role.get("name", "-"))
            self.id_var.set(role.get("id", "-"))

            self._build_init_number(role)
            self._load_draw_cost_from_role(role)
            self._load_victory_from_role(role)
            self._update_victory_preview()

            self.status.set(f"Loaded: {fn}")
        except Exception as e:
            self.status.set(f"Load failed: {e}")

    def _build_init_number(self, role):
        self._clear_init_line()

        init_number = role.get("init_number")
        if not isinstance(init_number, dict):
            self.status.set("init_number missing or invalid")
            return

        for key, cfg in init_number.items():
            label = cfg.get("label", key)
            value = cfg.get("number", 0)

            ttk.Label(self.init_line, text=label).pack(side="left", padx=(0, 4))

            v = tk.StringVar(value=str(to_int_min0(value)))
            self.value_vars[key] = v

            sp = ttk.Spinbox(
                self.init_line,
                from_=0,
                to=999999,
                textvariable=v,
                width=8
            )
            sp.pack(side="left", padx=(0, 14))
            sp.bind("<Button-1>", lambda e, _sp=sp: _sp.focus_set())

        # ==================
    # Victory (load/display)
    # ==================
    def _load_victory_from_role(self, role):
        v = role.get("victory")
        if not isinstance(v, dict):
            # json not set => UI shows blank (no defaults written)
            self.victory_id_var.set(self.victory_ids[0] if self.victory_ids else "")
            self.victory_n_var.set("0")
            self.victory_preview_var.set("(victory not set in json)")
            return

        vid = str(v.get("id", "")).strip()
        params = v.get("params", {}) if isinstance(v.get("params"), dict) else {}

        # only allow ids from global list
        if vid not in self.victory_defs:
            vid = self.victory_ids[0] if self.victory_ids else ""

        n = params.get("n", None)
        if n is None:
            # fallback to global default (for display)
            n = (self.victory_defs.get(vid, {}).get("param_defaults", {}) or {}).get("n", 0)

        self.victory_id_var.set(vid)
        self.victory_n_var.set(str(to_int_min0(n)))
        self._update_victory_preview()

    def _update_victory_preview(self):
        vid = self.victory_id_var.get().strip()
        n = to_int_min0(self.victory_n_var.get())

        info = self.victory_defs.get(vid)
        if not info:
            self.victory_preview_var.set("(unknown victory condition)")
            return

        tpl = info.get("label_template", vid)
        try:
            self.victory_preview_var.set(tpl.format(n=n))
        except Exception:
            self.victory_preview_var.set(tpl)

    # ------------------
    # save
    # ------------------
    def save(self):
        # =========================
        # Guard: must have role loaded
        # =========================
        if not self.role or not self.role_path:
            messagebox.showerror("Save", "No role loaded.")
            return

        # =========================
        # Write init_number back
        # =========================
        init_number = self.role.get("init_number")
        if not isinstance(init_number, dict):
            messagebox.showerror("Save", "init_number missing.")
            return

        for key, var in self.value_vars.items():
            init_number[key]["number"] = to_int_min0(var.get())

        # =========================
        # Write draw_card_cost back  (START)
        # =========================
        def _sanitize_res(x):
            x = str(x)
            allowed = {k for (k, _lab) in DRAW_RESOURCES}
            return x if x in allowed else "stamina"

        def _amt(var):
            return to_int_min0(var.get()) or 1  # default 1 if 0

        options = []

        if self.cost_a_enabled.get():
            options.append({"resource": _sanitize_res(self.cost_a_res.get()), "delta": -_amt(self.cost_a_amt)})

        if self.cost_b_enabled.get():
            options.append({"resource": _sanitize_res(self.cost_b_res.get()), "delta": -_amt(self.cost_b_amt)})

        options = options[:2]

        logic = self.cost_logic_var.get().upper()
        if logic not in DRAW_LOGICS:
            logic = "THEN"

        self.role["draw_card_cost"] = {
            "logic": logic,
            "options": options
        }
        # =========================
        # Write draw_card_cost back  (END)
        # =========================

        # =========================
        # Write victory back 
        # =========================
        vid = self.victory_id_var.get().strip()
        if vid not in self.victory_defs:
            messagebox.showerror("Save", "Invalid victory condition selected.")
            return

        n = to_int_min0(self.victory_n_var.get())

        self.role["victory"] = {
            "id": vid,
            "params": {"n": n}
        }

        # =========================
        # Save json file to disk
        # =========================
        try:
            save_json(self.role_path, self.role)
            self.status.set("Saved.")
            messagebox.showinfo("Saved", f"Updated:\n{self.role_path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))