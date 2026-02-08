import json, os
import tkinter as tk
from tkinter import ttk, messagebox

# ======================
# Paths & IO
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVENTS_DIR = os.path.join(ROOT, "data", "events")
GLOBAL_EVENT_DEFS = os.path.join(ROOT, "data", "global_defs.json")

def list_event_files():
    if not os.path.isdir(EVENTS_DIR):
        return []
    return sorted(f for f in os.listdir(EVENTS_DIR) if f.endswith(".json"))

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
# Global defs (read-only)
# ======================
def load_global_effect_defs():
    """
    Reads data/global_event_effect_defs.json
    Returns: (defs_map, ids_in_order)
    """
    try:
        with open(GLOBAL_EVENT_DEFS, "r", encoding="utf-8") as f:
            obj = json.load(f)
        arr = obj.get("global_effect_defs", [])
        if not isinstance(arr, list):
            return {}, []
        mp, ids = {}, []
        for it in arr:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            eid = it["id"]
            ids.append(eid)
            mp[eid] = {
                "label_template": it.get("label_template", eid),
                "param_defaults": it.get("param_defaults", {"amount": 1}),
            }
        return mp, ids
    except Exception:
        return {}, []

# ======================
# Tab 2: Event UI
# ======================
class EventTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        # ----- state -----
        self.event = None
        self.event_path = None
        self.defs, self.def_ids = load_global_effect_defs()

        # ----- header -----
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Event (Tab2)", font=("Arial", 14, "bold")).pack(side="left")
        ttk.Button(head, text="Save the change", command=self.save).pack(side="right")

        # ----- selector -----
        sel = ttk.Frame(self)
        sel.pack(fill="x", pady=(12, 10))
        ttk.Label(sel, text="Event file:").pack(side="left")

        self.combo_var = tk.StringVar()
        self.combo = ttk.Combobox(sel, textvariable=self.combo_var, state="readonly", width=44)
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.load_selected())

        # ----- basic -----
        info = ttk.LabelFrame(self, text="Basic (read-only)", padding=10)
        info.pack(fill="x")

        self.name_var = tk.StringVar(value="-")
        self.id_var = tk.StringVar(value="-")
        self._row(info, "name:", self.name_var)
        self._row(info, "id:", self.id_var)

        # ----- global effect -----
        box = ttk.LabelFrame(self, text="Global Effect", padding=10)
        box.pack(fill="x", pady=(10, 0))

        self.effect_id_var = tk.StringVar(value="")
        self.amount_var = tk.StringVar(value="1")
        self.preview_var = tk.StringVar(value="")

        row = ttk.Frame(box)
        row.pack(fill="x")

        ttk.Label(row, text="effect:", width=10).pack(side="left")
        self.effect_combo = ttk.Combobox(
            row, textvariable=self.effect_id_var,
            values=self.def_ids, state="readonly", width=26
        )
        self.effect_combo.pack(side="left", padx=(0, 12))

        ttk.Label(row, text="amount:").pack(side="left")
        self.amount_spin = ttk.Spinbox(row, from_=0, to=999, textvariable=self.amount_var, width=6)
        self.amount_spin.pack(side="left", padx=(6, 12))

        ttk.Label(row, textvariable=self.preview_var, foreground="#bbb", width=30)\
            .pack(side="left", padx=(12, 0))

        self.effect_id_var.trace_add("write", lambda *_: self._update_preview())
        self.amount_var.trace_add("write", lambda *_: self._update_preview())

        # ----- status -----
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, foreground="#666").pack(anchor="w", pady=(10, 0))

        # init list
        self.refresh_list(select_first=True)

    # ------------------
    # small helper
    # ------------------
    def _row(self, parent, label, var):
        r = ttk.Frame(parent)
        r.pack(fill="x", pady=2)
        ttk.Label(r, text=label, width=10).pack(side="left")
        ttk.Label(r, textvariable=var).pack(side="left")

    # ------------------
    # load event
    # ------------------
    def refresh_list(self, select_first=False):
        files = list_event_files()
        self.combo["values"] = files
        if files and select_first:
            self.combo.current(0)
            self.load_selected()

    def load_selected(self):
        fn = self.combo_var.get().strip()
        if not fn:
            return
        path = os.path.join(EVENTS_DIR, fn)
        try:
            ev = load_json(path)
            self.event = ev
            self.event_path = path

            self.name_var.set(ev.get("name", "-"))
            self.id_var.set(ev.get("id", "-"))

            self._load_global_effect_from_event(ev)
            self._update_preview()

            self.status.set(f"Loaded: {fn}")
        except Exception as e:
            self.status.set(f"Load failed: {e}")

    def _load_global_effect_from_event(self, ev):
        ge = ev.get("global_effect")
        if not isinstance(ge, dict):
            # JSON没有配置就显示空（不写默认）
            self.effect_id_var.set("")
            self.amount_var.set("1")
            self.preview_var.set("(global_effect not set)")
            return

        eid = str(ge.get("id", "")).strip()
        params = ge.get("params", {}) if isinstance(ge.get("params"), dict) else {}

        # only allow from defs
        if eid not in self.defs:
            self.effect_id_var.set("")
            self.amount_var.set("1")
            self.preview_var.set("(unknown effect id)")
            return

        amt = params.get("amount", None)
        if amt is None:
            amt = (self.defs[eid].get("param_defaults", {}) or {}).get("amount", 1)

        self.effect_id_var.set(eid)
        self.amount_var.set(str(to_int_min0(amt)))

    def _update_preview(self):
        eid = self.effect_id_var.get().strip()
        amt = to_int_min0(self.amount_var.get())

        info = self.defs.get(eid)
        if not info:
            self.preview_var.set("")
            return

        tpl = info.get("label_template", eid)
        try:
            self.preview_var.set(tpl.format(amount=amt))
        except Exception:
            self.preview_var.set(str(tpl))

    # ------------------
    # save
    # ------------------
    def save(self):
        if not self.event or not self.event_path:
            messagebox.showerror("Save", "No event loaded.")
            return

        eid = self.effect_id_var.get().strip()
        if not eid:
            # empty => remove global_effect
            if "global_effect" in self.event:
                del self.event["global_effect"]
        else:
            if eid not in self.defs:
                messagebox.showerror("Save", "Invalid global effect selected.")
                return
            amt = to_int_min0(self.amount_var.get())
            self.event["global_effect"] = {"id": eid, "params": {"amount": amt}}

        try:
            save_json(self.event_path, self.event)
            self.status.set("Saved.")
            messagebox.showinfo("Saved", f"Updated:\n{self.event_path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))