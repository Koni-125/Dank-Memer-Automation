import json
import re
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from aiohttp import web


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Commands driven by the normal rotation loop (main.py commands_dict keys).
ROTATION_COMMANDS = [
    "trivia", "dig", "fish", "hunt", "pm", "beg", "pet", "scratch",
    "hl", "search", "tidy", "dep_all", "stream", "work", "daily",
    "crime", "bal", "adventure", "blackjack",
]

try:
    from cogs.onboarding import onboarding_commands as _ONBOARDING_COMMANDS

    ONBOARDING_COMMAND_KEYS = list(_ONBOARDING_COMMANDS.keys())
except Exception:
    ONBOARDING_COMMAND_KEYS = [
        "beg", "search", "tidy", "inventory", "bal", "hunt", "dig",
        "work", "sell", "buy", "cointoss", "slots", "snakeeyes",
        "roulette", "blackjack", "use cheese", "item", "title",
        "profile", "daily", "hl", "multipliers", "crime", "giveaway",
        "craft", "farm", "quests", "pm", "currencylog",
        "notifications", "lottery", "dep_all", "settings",
        "advancements", "achievements", "badges", "collection",
        "leaderboard", "skins", "play", "fish", "pets", "pets view",
        "pets care", "pets rooms", "help",
    ]


class DashboardState:
    def __init__(self, log_dir=None):
        self.started_at = time.time()
        self._bots = []
        self._logs = deque(maxlen=1200)
        self._lock = threading.Lock()
        self._log_dir = Path(log_dir) if log_dir is not None else None
        if self._log_dir is not None:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def _bot_log_path(self):
        # Daily-rotated bot/debug log, e.g. logs/bot-2026-09-14.log
        day = datetime.now().strftime("%Y-%m-%d")
        return self._log_dir / f"bot-{day}.log"

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
        # Persist bot/debug logs to logs/bot-YYYY-MM-DD.log (best effort).
        if self._log_dir is not None:
            try:
                with open(self._bot_log_path(), "a", encoding="utf-8") as f:
                    f.write(
                        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"{level.upper().ljust(8)} | {clean}\n"
                    )
            except OSError:
                pass

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
        try:
            limit = int(request.query.get("limit", "200"))
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 1200))
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

    async def api_commands(_request):
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cmds = data.get("commands", {}) or {}
        rotation = [k for k in ROTATION_COMMANDS if k in cmds]
        # Onboarding-only = known onboarding keys not in the normal rotation.
        onboarding_only = [k for k in ONBOARDING_COMMAND_KEYS if k in cmds and k not in ROTATION_COMMANDS]
        # Anything else in settings.json that is neither (future-proofing).
        other = [k for k in cmds if k not in ROTATION_COMMANDS and k not in ONBOARDING_COMMAND_KEYS]
        return web.json_response(
            {
                "commands": cmds,
                "groups": {
                    "rotation": rotation,
                    "onboarding_only": onboarding_only,
                    "other": other,
                },
            }
        )

    app.router.add_get("/", index)
    app.router.add_get("/api/overview", api_overview)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/settings", api_settings_get)
    app.router.add_put("/api/settings", api_settings_put)
    app.router.add_post("/api/settings/reload", api_settings_reload)
    app.router.add_get("/api/commands", api_commands)
    return app


def run_dashboard_server(state: DashboardState, settings_path: Path, root_dir: Path, host="127.0.0.1", port=3000):
    app = create_dashboard_app(state, settings_path, root_dir)
    web.run_app(app, host=host, port=port, handle_signals=False, print=None)
