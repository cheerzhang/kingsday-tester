import json
import os
import tkinter as tk
from tkinter import ttk

# ======================
# Paths & IO
# ======================
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLES_DIR = os.path.join(ROOT, "data", "roles")
GLOBAL_VICTORY_DEFS = os.path.join(ROOT, "data", "global_defs.json")

ROLE_ORDER = [
    "role_finn",
    "role_tourist",
    "role_vendor",
    "role_food_vendor",
    "role_performer",
    "role_volunteer",
]

STAT_ORDER = [
    "stamina",
    "curiosity",
    "money",
    "product",
    "orange_product",
    "orange_wear_product",
]

STAT_LABELS = {
    "stamina": "体力",
    "curiosity": "好奇心",
    "money": "金钱",
    "product": "普通物品",
    "orange_product": "橙色物品(未佩戴)",
    "orange_wear_product": "橙色物品(已佩戴)",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_victory_defs():
    try:
        obj = load_json(GLOBAL_VICTORY_DEFS)
        arr = obj.get("victory_defs", [])
        if not isinstance(arr, list):
            return {}
        out = {}
        for it in arr:
            if not isinstance(it, dict):
                continue
            vid = it.get("id")
            if not vid:
                continue
            out[vid] = {
                "label_template": it.get("label_template", vid),
                "param_defaults": it.get("param_defaults", {"n": 0}),
            }
        return out
    except Exception:
        return {}


def format_victory(role, victory_defs):
    v = role.get("victory", {})
    if not isinstance(v, dict):
        return "-"
    vid = v.get("id") or "-"
    params = v.get("params", {})
    if not isinstance(params, dict):
        params = {}
    tpl = victory_defs.get(vid, {}).get("label_template", vid)
    defaults = victory_defs.get(vid, {}).get("param_defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}
    merged = dict(defaults)
    merged.update(params)
    try:
        return tpl.format(**merged)
    except Exception:
        return f"{vid} {merged}"


def format_stats(role):
    init_number = role.get("init_number", {})
    if not isinstance(init_number, dict):
        return "-"
    lines = []
    for key in STAT_ORDER:
        val = init_number.get(key, {}).get("number")
        if val is None:
            continue
        label = STAT_LABELS.get(key, key)
        lines.append(f"{label}: {val}")
    return "\n".join(lines) if lines else "-"


def format_draw_cost(role):
    dc = role.get("draw_card_cost", {})
    if not isinstance(dc, dict):
        return "-"
    logic = str(dc.get("logic", "THEN")).upper()
    options = dc.get("options", [])
    if not isinstance(options, list) or not options:
        return "-"

    def fmt_costs(costs):
        parts = []
        for c in costs:
            if not isinstance(c, dict):
                continue
            res = c.get("resource", "")
            delta = c.get("delta", 0)
            sign = "+" if int(delta) > 0 else ""
            parts.append(f"{res} {sign}{delta}")
        return ", ".join(parts) if parts else "-"

    opt_strs = [fmt_costs(o.get("costs", [])) for o in options if isinstance(o, dict)]
    if logic == "OR":
        return "或： " + " / ".join(opt_strs)
    return "依次： " + " -> ".join(opt_strs)


def format_skill(role):
    skill = role.get("active_skill", {})
    desc = role.get("active_skill_desc")
    if isinstance(desc, str) and desc.strip():
        return desc.strip()
    if not isinstance(skill, dict):
        return "无主动技能"
    return "主动技能"


def format_draw_cost_desc(role):
    dc = role.get("draw_card_cost", {})
    if not isinstance(dc, dict):
        return "-"
    logic = str(dc.get("logic", "THEN")).upper()
    options = dc.get("options", [])
    if not isinstance(options, list) or not options:
        return "-"

    def label(res):
        return STAT_LABELS.get(res, res)

    def fmt_costs(costs):
        parts = []
        for c in costs:
            if not isinstance(c, dict):
                continue
            res = c.get("resource", "")
            delta = int(c.get("delta", 0))
            sign = "+" if delta > 0 else ""
            parts.append(f"{label(res)} {sign}{delta}")
        return "，".join(parts) if parts else "-"

    opt_strs = [fmt_costs(o.get("costs", [])) for o in options if isinstance(o, dict)]
    if logic == "OR":
        return "抽卡代价（二选一）： " + " / ".join(opt_strs)
    return "抽卡代价： " + " -> ".join(opt_strs)


class RoleTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=12)

        victory_defs = load_victory_defs()

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="Role Cards (Tab1, Read Only)", font=("Arial", 14, "bold")).pack(side="left")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, pady=(12, 0))

        row = 0
        for rid in ROLE_ORDER:
            path = os.path.join(ROLES_DIR, f"{rid}.json")
            if not os.path.exists(path):
                continue
            role = load_json(path)
            name = role.get("name", rid)

            front = ttk.LabelFrame(wrap, text=f"{name} (Front)", padding=10)
            back = ttk.LabelFrame(wrap, text=f"{name} (Back)", padding=10)

            front.grid(row=row, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
            back.grid(row=row, column=1, sticky="nsew", padx=(0, 0), pady=(0, 10))

            front_text = "\n".join([
                f"Name: {name}",
                f"ID: {rid}",
                "",
                "Init Stats:",
                format_stats(role),
                "",
                "Victory:",
                format_victory(role, victory_defs),
            ])
            back_text = "\n".join([
                "Ability:",
                format_skill(role),
                "",
                "Draw Cost:",
                format_draw_cost_desc(role),
            ])

            ttk.Label(front, text=front_text, justify="left").pack(anchor="w")
            ttk.Label(back, text=back_text, justify="left").pack(anchor="w")

            row += 1

        wrap.columnconfigure(0, weight=1)
        wrap.columnconfigure(1, weight=1)
