import json
import re
import threading
import time
from collections import deque
from pathlib import Path

from aiohttp import web


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class DashboardState:
    def __init__(self):
        self.started_at = time.time()
        self._bots = []
        self._logs = deque(maxlen=1200)
        self._lock = threading.Lock()

    def register_bot(self, bot):
        with self._lock:
            if bot not in self._bots:
                self._bots.append(bot)

    def unregister_bot(self, bot):
        with self._lock:
            if bot in self._bots:
                self._bots.remove(bot)

    def add_log(self, level, message):
        clean = ANSI_RE.sub("", str(message))
        with self._lock:
            self._logs.append(
                {
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "level": level.lower(),
                    "message": clean,
                }
            )

    def snapshot(self):
        with self._lock:
            bots = list(self._bots)
            logs = list(self._logs)

        bot_rows = []
        for bot in bots:
            worth = getattr(bot, "worth", {}) or {}
            bot_rows.append(
                {
                    "channel_id": getattr(bot, "channel_id", None),
                    "state": bool(getattr(bot, "state", False)),
                    "hold_command": bool(getattr(bot, "hold_command", False)),
                    "last_command": getattr(bot, "last_sent_command", None),
                    "worth": {
                        "coins": worth.get("coins", 0),
                        "inventory": worth.get("inventory", 0),
                        "net": worth.get("net", worth.get("worth", 0)),
                    },
                }
            )

        total_commands = sum(int(getattr(b, "sent_command_count", 0)) for b in bots)
        return {
            "uptime_s": int(time.time() - self.started_at),
            "bots": bot_rows,
            "total_commands": total_commands,
            "logs": logs,
        }


def create_dashboard_app(state: DashboardState, settings_path: Path, root_dir: Path):
    app = web.Application()

    async def index(_request):
        return web.FileResponse(root_dir / "dashboard" / "index.html")

    async def api_overview(_request):
        return web.json_response(state.snapshot())

    async def api_logs(request):
        limit = int(request.query.get("limit", "200"))
        snap = state.snapshot()
        return web.json_response({"logs": snap["logs"][-limit:]})

    async def api_settings_get(_request):
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return web.json_response(data)

    async def api_settings_put(request):
        incoming = await request.json()
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(incoming, f, indent=4)
        return web.json_response({"ok": True})

    async def api_settings_reload(_request):
        with open(settings_path, "r", encoding="utf-8") as f:
            fresh = json.load(f)
        with state._lock:
            bots = list(state._bots)
        for bot in bots:
            bot.settings_dict = fresh
        return web.json_response({"ok": True, "reloaded_bots": len(bots)})

    app.router.add_get("/", index)
    app.router.add_get("/api/overview", api_overview)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/settings", api_settings_get)
    app.router.add_put("/api/settings", api_settings_put)
    app.router.add_post("/api/settings/reload", api_settings_reload)
    return app


def run_dashboard_server(state: DashboardState, settings_path: Path, root_dir: Path, host="127.0.0.1", port=3000):
    app = create_dashboard_app(state, settings_path, root_dir)
    web.run_app(app, host=host, port=port, handle_signals=False, print=None)
