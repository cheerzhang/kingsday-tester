import json
import os
import tkinter as tk
from tkinter import ttk

# ======================
# Paths & IO
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EVENTS_DIR = os.path.join(ROOT, "data", "events")
ROLES_DIR = os.path.join(ROOT, "data", "roles")
GLOBAL_DEFS = os.path.join(ROOT, "data", "global_defs.json")

ROLE_ORDER = [
    "role_finn",
    "role_tourist",
    "role_vendor",
    "role_food_vendor",
    "role_performer",
    "role_volunteer",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_role_names():
    out = {}
    for rid in ROLE_ORDER:
        path = os.path.join(ROLES_DIR, f"{rid}.json")
        if not os.path.exists(path):
            continue
        try:
            obj = load_json(path)
            out[rid] = obj.get("name", rid)
        except Exception:
            out[rid] = rid
    return out


def load_global_effect_defs():
    try:
        obj = load_json(GLOBAL_DEFS)
        arr = obj.get("global_effect_defs", [])
        if not isinstance(arr, list):
            return {}
        mp = {}
        for it in arr:
            if not isinstance(it, dict):
                continue
            eid = it.get("id")
            if not eid:
                continue
            mp[eid] = {
                "label_template": it.get("label_template", eid),
                "param_defaults": it.get("param_defaults", {}),
            }
        return mp
    except Exception:
        return {}


def list_event_files():
    if not os.path.isdir(EVENTS_DIR):
        return []
    # only event_1..event_16 in order
    files = []
    for i in range(1, 17):
        fn = f"event_{i}.json"
        path = os.path.join(EVENTS_DIR, fn)
        if os.path.exists(path):
            files.append(fn)
    return files


def format_global_effect(ev, defs_map):
    ge = ev.get("global_effect", {})
    if not isinstance(ge, dict):
        return "None"
    label = str(ge.get("label", "")).strip()
    if label:
        return label
    eid = str(ge.get("id", "")).strip()
    params = ge.get("params", {})
    if not isinstance(params, dict):
        params = {}
    info = defs_map.get(eid)
    if not info:
        return eid or "None"
    tpl = info.get("label_template", eid)
    merged = dict(info.get("param_defaults", {}) or {})
    merged.update(params)
    try:
        return tpl.format(**merged)
    except Exception:
        return str(tpl)


def format_role_effects(ev, role_names):
    effects = ev.get("role_effects", {})
    if not isinstance(effects, dict):
        return ["Role Effect: None"]
    lines = []
    for rid in ROLE_ORDER:
        if rid not in effects:
            continue
        reff = effects.get(rid)
        if reff is None:
            continue
        label = ""
        if isinstance(reff, dict):
            label = str(reff.get("label", "")).strip()
        role_name = role_names.get(rid, rid)
        if label:
            lines.append(f"Role Effect [{role_name}]: {label}")
        else:
            lines.append(f"Role Effect [{role_name}]: (no label)")
    return lines if lines else ["Role Effect: None"]


class EventTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        self.role_names = load_role_names()
        self.defs_map = load_global_effect_defs()

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Event Cards (Tab2, Read Only)", font=("Arial", 14, "bold")).pack(side="left")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(12, 0))

        files = list_event_files()
        col_count = 4
        row = 0
        col = 0

        for fn in files:
            path = os.path.join(EVENTS_DIR, fn)
            try:
                ev = load_json(path)
            except Exception:
                continue

            name = ev.get("name", fn)
            eid = ev.get("id", fn)
            ge = format_global_effect(ev, self.defs_map)
            role_lines = format_role_effects(ev, self.role_names)

            card = ttk.LabelFrame(wrap, text=f"{name}", padding=8)
            card.grid(row=row, column=col, sticky="nsew", padx=(0, 10), pady=(0, 10))

            lines = [
                f"ID: {eid}",
                "",
                "Global Effect:",
                ge,
                "",
            ] + role_lines

            ttk.Label(card, text="\n".join(lines), justify="left").pack(anchor="w")

            col += 1
            if col >= col_count:
                col = 0
                row += 1

        for c in range(col_count):
            wrap.columnconfigure(c, weight=1)
