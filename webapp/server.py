from __future__ import annotations

import sys
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parents[1]
PYAPP_DIR = BASE_DIR / "pyapp"
if str(PYAPP_DIR) not in sys.path:
    sys.path.insert(0, str(PYAPP_DIR))

from core_logic import load_role_by_id
from game_flow import GameFlow
from game_logic import init_game_runtime, load_all_roles_min, load_current_game, load_player_gamestate, reset_runtime


class StartRequest(BaseModel):
    selected_role_ids: list[str] = Field(default_factory=list)


class ActionRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class WebGameSession:
    def __init__(self) -> None:
        self.flow: GameFlow | None = None
        self.current_ui: dict[str, Any] = {}
        self.log_history: list[str] = []

    def reset(self) -> None:
        reset_runtime()
        self.flow = None
        self.current_ui = {}
        self.log_history = []

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, tuple) and len(result) == 2:
            kind, payload = result
            if kind == "need_choice":
                out = dict(payload) if isinstance(payload, dict) else {}
                out["ui_mode"] = "DRAW_COST_CHOICE"
                return out
            if isinstance(payload, dict):
                return payload
            return {"ui_mode": "TURN"}

        if isinstance(result, dict):
            return result

        return {"ui_mode": "TURN"}

    def _collect_players(self) -> list[dict[str, Any]]:
        cur = load_current_game()
        players = cur.get("players", [])
        if not isinstance(players, list):
            players = []

        out: list[dict[str, Any]] = []
        for rid in players:
            role = load_role_by_id(rid)
            gs = load_player_gamestate(rid)
            draw_cfg = role.get("draw_card_cost") if isinstance(role.get("draw_card_cost"), dict) else {}
            active_skill = role.get("active_skill") if isinstance(role.get("active_skill"), dict) else {}
            victory = role.get("victory") if isinstance(role.get("victory"), dict) else {}
            out.append(
                {
                    "role_id": rid,
                    "role_name": role.get("name", rid),
                    "status": gs.get("status", {}),
                    "counters": gs.get("counters", {}),
                    "win_game": bool(gs.get("win_game")),
                    "role_meta": {
                        "draw_logic": draw_cfg.get("logic", "THEN"),
                        "draw_options": draw_cfg.get("options", []),
                        "active_skill": {
                            "id": active_skill.get("id", ""),
                            "name": active_skill.get("name", ""),
                            "description": active_skill.get("description", ""),
                        },
                        "victory": {
                            "id": victory.get("id", ""),
                            "description": victory.get("description", ""),
                        },
                    },
                }
            )
        return out

    def _pull_logs(self) -> None:
        if not self.flow:
            return
        self.log_history.extend(self.flow.consume_logs())

    def start(self, selected_role_ids: list[str]) -> dict[str, Any]:
        init_game_runtime(selected_role_ids)
        self.flow = GameFlow()
        first = self.flow.start_game()
        self.current_ui = self._normalize_result(first)
        self.log_history = []
        self._pull_logs()
        return self.state()

    def action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.flow:
            raise HTTPException(status_code=400, detail="Game not started")

        f = self.flow

        if action == "request_draw":
            result = f.request_draw()
        elif action == "choose_draw_cost":
            result = f.choose_draw_cost(int(params.get("index", -1)))
        elif action == "request_no_draw_choice":
            result = f.request_no_draw_choice()
        elif action == "use_active_skill":
            result = f.use_active_skill()
        elif action == "skip_turn":
            result = f.skip_turn()
        elif action == "trigger_role_effect":
            result = f.trigger_role_effect()
        elif action == "skip_role_effect":
            result = f.skip_role_effect()
        elif action == "event_choose_target":
            result = f.event_choose_target(str(params.get("target_id", "")))
        elif action == "watch_decide":
            result = f.watch_decide(str(params.get("target_id", "")), bool(params.get("watch", False)))
        elif action == "photo_choose_target":
            result = f.photo_choose_target(str(params.get("target_id", "")))
        elif action == "photo_consent":
            result = f.photo_consent(bool(params.get("agree", False)))
        elif action == "trade_choose_item":
            result = f.trade_choose_item(int(params.get("item_index", -1)))
        elif action == "trade_choose_partner":
            result = f.trade_choose_partner(str(params.get("partner_id", "")))
        elif action == "trade_consent":
            result = f.trade_consent(bool(params.get("agree", False)))
        elif action == "food_offer_decide":
            result = f.food_offer_decide(str(params.get("target_id", "")), bool(params.get("accept", False)))
        elif action == "perform_watch_decide":
            result = f.perform_watch_decide(str(params.get("target_id", "")), bool(params.get("watch", False)))
        elif action == "perform_watch_benefit":
            result = f.perform_watch_benefit(str(params.get("target_id", "")), str(params.get("choice", "")))
        elif action == "gift_choose_target":
            result = f.gift_choose_target(str(params.get("target_id", "")))
        elif action == "exchange_choose_target":
            result = f.exchange_choose_target(str(params.get("target_id", "")))
        elif action == "exchange_choose_option":
            result = f.exchange_choose_option(int(params.get("option_index", -1)))
        elif action == "exchange_consent":
            result = f.exchange_consent(bool(params.get("agree", False)))
        elif action == "volunteer_help":
            result = f.volunteer_help(bool(params.get("agree", False)))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        self.current_ui = self._normalize_result(result)
        self._pull_logs()
        return self.state()

    def state(self) -> dict[str, Any]:
        cur = load_current_game()
        event_info = self.flow.current_event_info if self.flow else None
        if not isinstance(event_info, dict):
            event_info = {}
        return {
            "game_started": self.flow is not None,
            "game_over": bool(cur.get("game_over")),
            "game_over_reason": cur.get("game_over_reason", ""),
            "rounds_completed": int(cur.get("rounds_completed", 0) or 0),
            "events_drawn": len(cur.get("events_drawn", []) if isinstance(cur.get("events_drawn"), list) else []),
            "ui": self.current_ui,
            "event_info": event_info,
            "players": self._collect_players(),
            "logs": self.log_history[-500:],
        }


app = FastAPI(title="Kingsday Tester Web")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "webapp" / "static")), name="static")

_session = WebGameSession()
_session_lock = Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


@app.get("/api/roles")
def list_roles() -> list[dict[str, Any]]:
    roles = load_all_roles_min()
    return sorted(roles, key=lambda x: x.get("name", ""))


@app.post("/api/game/reset")
def reset_game() -> dict[str, Any]:
    with _session_lock:
        _session.reset()
        return _session.state()


@app.post("/api/game/start")
def start_game(req: StartRequest) -> dict[str, Any]:
    with _session_lock:
        return _session.start(req.selected_role_ids)


@app.post("/api/game/action")
def game_action(req: ActionRequest) -> dict[str, Any]:
    with _session_lock:
        return _session.action(req.action, req.params)


@app.get("/api/game/state")
def game_state() -> dict[str, Any]:
    with _session_lock:
        return _session.state()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "webapp" / "static" / "index.html")
