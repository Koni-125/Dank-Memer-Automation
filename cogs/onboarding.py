import asyncio
import json
import re
import time
from pathlib import Path

import components_v2

from discord.ext import commands, tasks

from utils.onboarding import ONBOARDING_LEVELS

# Once the account reaches this level, onboarding ends and the normal
# commands.py rotation takes over.
TARGET_LEVEL = 18

LOCKED_STATE_FILE = Path(__file__).resolve().parent.parent / "data" / "bot_state.json"
SETTINGS_FILE = Path(__file__).resolve().parent.parent / "settings.json"

# Commands used only to satisfy onboarding objectives. They must NOT run on the
# normal rotation in cogs/commands.py; they only run while a pending objective.
onboarding_commands = {
    "beg": "beg",
    "search": "search",
    "tidy": "tidy",
    "inventory": "inv",
    "bal": "balance",
    "hunt": "hunt",
    "dig": "dig",
    "work": "work shift",
    "sell": "shop sell",
    "buy": "shop view",
    "cointoss": "cointoss 50000",
    "slots": "slots 50000",
    "snakeeyes": "snakeeyes 50000",
    "roulette": "roulette 50000",
    "blackjack": "blackjack 50000",
    "use cheese": "use shredded cheese",
    "item": "item horseshoe",
    "title": "title set Newbie",
    "profile": "profile",
    "daily": "daily",
    "hl": "highlow",
    "multipliers": "multipliers luck",
    "crime": "crime",
    "giveaway": "giveaway view",
    "craft": "craft",
    "farm": "farm view",
    "quests": "quests",
    "pm": "postmemes",
    "currencylog": "currencylog",
    "notifications": "notifications list",
    "lottery": "lottery buy 1",
    "dep_all": "deposit",
    "settings": "settings",
    "advancements": "advancements levels",
    "achievements": "achievements",
    "badges": "badges list",
    "collection": "collection",
    "leaderboard": "leaderboard stats",
    "skins": "skins view",
    "play": "play",
    "fish": "fish catch",
    "pets": "pets",
    "pets view": "pets view",
    "pets care": "pets care",
    "pets rooms": "pets rooms",
    "help": "help command use",
}

# Cooldown floor per onboarding command (mirrors commands_min_cd).
onboarding_min_cd = {
    "beg": 40,
    "search": 25,
    "tidy": 20,
    "inventory": 60,
    "bal": 60,
    "hunt": 20,
    "dig": 20,
    "work": 60 * 30,
    "sell": 30,
    "buy": 300,
    "cointoss": 30,
    "slots": 30,
    "snakeeyes": 30,
    "roulette": 30,
    "blackjack": 60,
    "use cheese": 60,
    "item": 60,
    "title": 60,
    "profile": 60,
    "daily": 3600 * 12,
    "hl": 10,
    "multipliers": 60,
    "crime": 40,
    "giveaway": 60,
    "craft": 60,
    "farm": 60,
    "quests": 60,
    "pm": 20,
    "currencylog": 60,
    "notifications": 60,
    "lottery": 60,
    "dep_all": 0,
    "settings": 60,
    "advancements": 60,
    "achievements": 60,
    "badges": 60,
    "collection": 60,
    "leaderboard": 60,
    "skins": 60,
    "play": 60,
    "fish": 12,
    "pets": 60,
    "pets view": 60,
    "pets care": 60,
    "pets rooms": 60,
    "help": 60,
}

gambling_commands = {
    "cointoss",
    "slots",
    "snakeeyes",
    "roulette",
    "blackjack",
}

_ONBOARDING_LEVEL_RE = re.compile(r"Level\s+(\d+)\s+Reached")
_ONBOARDING_TASK_RE = re.compile(r"</([a-z_ ]+):\d+>")
_ONBOARDING_TASK_RE_PLAIN = re.compile(r"`/([a-z_ ]+)`")
_ONBOARDING_COUNT_RE = re.compile(r"`\s*([\d,]+)\s*/\s*([\d,]+)\s*`")
_ONBOARDING_DESC_RE = re.compile(r"`[\d, ]+/[\d, ]+`\s*(?:<:[^:]+:\d+>\s*)*(.+)$")
_OBJECTIVES_BUTTON_RE = re.compile(r"next objectives", re.IGNORECASE)


def _load_state():
    try:
        with open(LOCKED_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("locked", [])), data.get("current_level")
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        pass
    legacy = LOCKED_STATE_FILE.parent / "locked_commands.json"
    try:
        with open(legacy, "r", encoding="utf-8") as f:
            return set(json.load(f)), None
    except (FileNotFoundError, json.JSONDecodeError, TypeError):
        return set(), None


def _save_state(locked_set, current_level):
    LOCKED_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCKED_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"locked": sorted(locked_set), "current_level": current_level},
            f,
            indent=2,
        )


def _onboarding_rest():
    # Smallest positive cooldown difference so the loop rests long enough to
    # avoid overlapping commands.
    cds = sorted(cd for cd in onboarding_min_cd.values() if cd > 0)
    if not cds:
        return 1
    gap = min(b - a for a, b in zip(cds, cds[1:])) if len(cds) > 1 else cds[0]
    return max(min(gap, cds[0]), 1)


class Onboarding(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sleep_time = _onboarding_rest()
        self.minCommandCD = self.bot.settings_dict["settings"]["cooldowns"]["minCommandDelay"]
        self.maxCommandCD = self.bot.settings_dict["settings"]["cooldowns"]["maxCommandDelay"]
        self.auto_disabled = {}
        self.active_onboarding_tasks = set()
        self._pending_passive = set()
        self.current_level = None
        self._details_fetched = False
        self._details_seen = False
        self._last_scratch_sent = 0
        self.locked_commands, saved_level = _load_state()
        for cmd in self.locked_commands:
            try:
                self.bot.settings_dict["commands"][cmd]["enabled"] = False
            except KeyError:
                pass
        self.current_level = saved_level
        if self.current_level is not None:
            self._enable_hardcoded_objectives()
            # If already at/above the target level, end onboarding now.
            self._maybe_complete()
        for command in onboarding_commands:
            self.bot.last_ran.setdefault(command, 0)
        self.bot.message_dispatcher.register(self.log_messages)

    def enabled(self):
        try:
            return bool(
                self.bot.settings_dict["settings"]["onboarding"]["enabled"]
            )
        except (KeyError, TypeError):
            return False

    def _set_enabled(self, value):
        try:
            was_enabled = bool(
                self.bot.settings_dict["settings"]["onboarding"]["enabled"]
            )
        except (KeyError, TypeError):
            was_enabled = False
        try:
            self.bot.settings_dict["settings"]["onboarding"]["enabled"] = bool(value)
        except (KeyError, TypeError):
            self.bot.settings_dict.setdefault("settings", {})["onboarding"] = {
                "enabled": bool(value)
            }
        if not was_enabled and value:
            # Onboarding just turned on: (re)fetch details via /scratch once.
            self._details_fetched = False
            self.bot.log("Onboarding mode enabled - fetching details via /scratch", "yellow")
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.bot.settings_dict, f, indent=4)
        except OSError as e:
            self.bot.log(f"Failed to persist onboarding toggle: {e}", "red")

    def _save_current(self):
        _save_state(self.locked_commands, self.current_level)

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        joined = "\n".join(texts)

        # Parse level/progress/objectives first so that locked responses
        # (which embed the current level's task rows) also update our task
        # list, then handle lock/backoff bookkeeping.
        await self._handle_onboarding(message, texts, joined)

        if any(
            "You have not unlocked this feature yet!" in text for text in texts
        ):
            self._set_enabled(True)
            self._disable_locked(message)
            return

        if any(
            "You already have a command in progress" in text
            or "Too spicy" in text
            for text in texts
        ):
            self._backoff(message)
            return

    async def _handle_onboarding(self, message, texts, joined):
        if "Reached" in joined:
            self._set_enabled(True)
            level_match = _ONBOARDING_LEVEL_RE.search(joined)
            level = level_match.group(1) if level_match else None
            if level is not None:
                self.current_level = int(level)
                self._save_current()
            unlocked = _ONBOARDING_TASK_RE.findall(joined)
            self.bot.log(
                f"Onboarding: Level {level} reached! "
                f"Unlocked: {', '.join(unlocked) or '?'}. "
                f"Re-probing locked commands.",
                "green",
            )
            # New level's tasks may not be known yet (or exist in the map);
            # re-fetch full details via /scratch on the next loop iteration.
            self._details_fetched = False
            self._details_seen = False
            self._last_scratch_sent = 0
            for cmd in list(self.auto_disabled):
                self.auto_disabled[cmd] = 0
            self.active_onboarding_tasks.clear()
            self._enable_hardcoded_objectives()
            for button in message.buttons:
                if button.label and _OBJECTIVES_BUTTON_RE.search(button.label):
                    await self.bot.click_button(button)
                    break

        if (
            "Progress" not in joined
            and "not unlocked" not in joined
            and "Objectives" not in joined
        ):
            return

        # The locked/progress message embeds the current level's header as
        # "**Level X**" (locked) or "Level X Progress" (progress). Keep the
        # saved level in sync so task tracking matches the actual level.
        level_match = re.search(r"Level\s+(\d+)", joined)
        if level_match:
            self._details_seen = True
            new_level = int(level_match.group(1))
            if new_level != self.current_level:
                self.current_level = new_level
                self._save_current()
                self.bot.log(
                    f"Onboarding: now on level {new_level} - re-probing locks",
                    "yellow",
                )
                for cmd in list(self.auto_disabled):
                    self.auto_disabled[cmd] = 0

        seen = set()
        pending = set()
        pending_passive = set()
        for line in joined.splitlines():
            count = _ONBOARDING_COUNT_RE.search(line)
            task = _ONBOARDING_TASK_RE.search(line)
            if not task:
                task = _ONBOARDING_TASK_RE_PLAIN.search(line)
            if not count and not task:
                continue
            cur = int(count.group(1).replace(",", "")) if count else 0
            tot = int(count.group(2).replace(",", "")) if count else 2

            # Tasks without a slash-command reference (e.g. "Run 20 more
            # commands") can't be driven by sending a command, so track them
            # separately so completion doesn't fire before they're done.
            if not task:
                desc_match = _ONBOARDING_DESC_RE.search(line)
                desc = desc_match.group(1).strip() if desc_match else line.strip()
                # Some tasks are written in prose but map to a command, e.g.
                # "Catch 15 fish" -> fish. Match against known command names.
                key = self._desc_to_key(desc)
                if key is not None:
                    seen.add(key)
                    if cur < tot:
                        pending.add(key)
                        try:
                            cfg = self.bot.settings_dict["commands"][key]
                        except KeyError:
                            pass
                        else:
                            if not cfg["enabled"]:
                                cfg["enabled"] = True
                                self.bot.log(
                                    f"Onboarding: enabling '{key}' ({cur}/{tot}) from prose task",
                                    "yellow",
                                )
                    continue
                if cur < tot:
                    pending_passive.add(desc)
                else:
                    pending_passive.discard(desc)
                continue

            key = self._slash_to_key(task.group(1))
            if key is None:
                continue
            seen.add(key)
            if cur >= tot:
                continue
            pending.add(key)
            try:
                cfg = self.bot.settings_dict["commands"][key]
            except KeyError:
                continue
            if not cfg["enabled"]:
                cfg["enabled"] = True
                self.bot.log(
                    f"Onboarding: enabling '{key}' ({cur}/{tot}) to complete its task",
                    "yellow",
                )

        if level_match:
            # This message lists the *current* level's tasks, so treat it as
            # authoritative: drop tasks that are no longer shown (e.g. a
            # completed previous level like craft/farm) and keep only the ones
            # still pending.
            self.active_onboarding_tasks = pending
            self._pending_passive = pending_passive
        else:
            for key in pending:
                self.active_onboarding_tasks.add(key)
            for key in seen - pending:
                self.active_onboarding_tasks.discard(key)
            self._pending_passive |= pending_passive

        self._maybe_complete()

    def _maybe_complete(self):
        # When the account reaches the target level, stop onboarding so the
        # normal commands.py rotation takes over.
        if self.current_level is None:
            return
        if self.current_level < TARGET_LEVEL:
            return
        if not self.enabled():
            return
        self._set_enabled(False)
        self.bot.log(
            f"Onboarding complete (level {self.current_level} >= {TARGET_LEVEL}). "
            "Disabled onboarding mode; normal commands resumed.",
             "green",
        )

    def _enable_hardcoded_objectives(self):
        # Enable only the *current* level's commands so tasks from earlier
        # (already completed) levels are not re-run. Unlock entries still clear
        # persisted locks across all higher levels.
        if self.current_level is None:
            return
        changed = False
        info = ONBOARDING_LEVELS.get(self.current_level, {})
        for cmd in info.get("commands", []):
            # Market handling is paused until the user decides how to proceed.
            if cmd == "market":
                continue
            self.active_onboarding_tasks.add(cmd)
            try:
                cfg = self.bot.settings_dict["commands"][cmd]
            except KeyError:
                continue
            if not cfg["enabled"]:
                cfg["enabled"] = True
                self.bot.log(
                    f"Onboarding L{self.current_level}: enabling '{cmd}'", "yellow"
                )
            if cmd in self.locked_commands:
                self.locked_commands.discard(cmd)
                changed = True
        for level, level_info in ONBOARDING_LEVELS.items():
            if level < self.current_level:
                continue
            for cmd in level_info.get("unlocks", []):
                self.auto_disabled.pop(cmd, None)
                if cmd in self.locked_commands:
                    self.locked_commands.discard(cmd)
                    changed = True
        if changed:
            self._save_current()

    def _slash_to_key(self, name):
        for key, trigger in onboarding_commands.items():
            if key == name or trigger == name:
                return key
        key = {
            "balance": "bal",
            "deposit": "dep_all",
            "highlow": "hl",
            "postmemes": "pm",
            "shop sell": "sell",
            "shop view": "buy",
            "shop buy": "buy",
            "pets": "pet",
            "inv": "inventory",
            "use": "use cheese",
        }.get(name)
        if key is not None:
            return key
        # Market handling is paused until the user decides how to proceed, so
        # don't auto-register market task commands.
        if name.startswith("market"):
            return None
        # Unknown objective command: register it on the fly so the onboarding
        # loop can drive it (send_slash resolves subcommands automatically).
        # E.g. "currencylog", "lottery buy 1", "notifications list".
        normalized = name.replace(" ", " ")
        if normalized and normalized not in onboarding_commands:
            onboarding_commands[normalized] = normalized
            onboarding_min_cd.setdefault(normalized, 60)
            self.bot.settings_dict.setdefault("commands", {}).setdefault(
                normalized, {"enabled": True, "delay": 60}
            )
            self.bot.last_ran.setdefault(normalized, 0)
            self.bot.log(
                f"Onboarding: auto-registered unknown task command '{normalized}'",
                "yellow",
            )
        return normalized

    def _desc_to_key(self, desc):
        # Map prose task descriptions to command keys, e.g. "Catch 15 fish",
        # "Rename your pet rock (/pets view ...)" -> "pets view".
        lower = desc.lower()
        # Specific mappings for tasks whose prose differs from the command.
        if "shredded cheese" in lower:
            return "use cheese"
        # Prefer the full trigger match first (e.g. "pets view" not just "pets")
        # so subcommand tasks map to the right key.
        for key, trigger in onboarding_commands.items():
            if trigger in lower:
                return key
        for key, trigger in onboarding_commands.items():
            name = trigger.split()[0]
            if name in lower:
                return key
        for name in ("balance", "highlow", "postmemes", "deposit"):
            if name in lower:
                return self._slash_to_key(name)
        return None

    def _disable_locked(self, message):
        replied = ""
        if message.referenced_message is not None:
            replied = message.referenced_message.content or ""
        command = self._find_command(replied)
        if command is None:
            return
        try:
            self.bot.settings_dict["commands"][command]["enabled"] = False
        except KeyError:
            return
        self.bot.last_ran[command] = time.time()
        self.locked_commands.add(command)
        self._save_current()
        self.auto_disabled[command] = time.time() + self.bot.random.uniform(
            15 * 60, 60 * 60
        )
        self.bot.log(
            f"'{command}' is locked on this account (onboarding). "
            f"Disabled it, will retry in ~{int(self.auto_disabled[command] - time.time()) // 60}m.",
            "yellow",
        )

    def _backoff(self, message):
        replied = ""
        if message.referenced_message is not None:
            replied = message.referenced_message.content or ""
        command = self._find_command(replied)
        if command is None:
            return
        backoff = self.get_cooldown(command)
        self.bot.last_ran[command] = time.time() + max(backoff, 30)
        self.bot.log(
            f"'{command}' not ready yet (command in progress / cooldown). "
            f"Backing off ~{max(backoff, 30)}s.",
            "yellow",
        )

    def _find_command(self, content):
        for name, trigger in onboarding_commands.items():
            if content and f"pls {trigger}" in content:
                return name
        return None

    def _probe_locked_commands(self):
        now = time.time()
        for command, probe_at in list(self.auto_disabled.items()):
            if now < probe_at:
                continue
            try:
                self.bot.settings_dict["commands"][command]["enabled"] = True
                self.bot.last_ran[command] = 0
            except KeyError:
                pass
            del self.auto_disabled[command]
            if command in self.locked_commands:
                self.locked_commands.discard(command)
                self._save_current()
            self.bot.log(
                f"Re-probing '{command}' in case it unlocked...", "yellow"
            )

    def get_cooldown(self, command_name):
        cd = self.bot.settings_dict["commands"][command_name]["delay"]
        min_cd = onboarding_min_cd.get(command_name, 0)
        return cd if cd >= min_cd else min_cd

    def should_run(self, command_name):
        if (
            not self.bot.settings_dict["commands"][command_name]["enabled"]
            or not self.bot.state
        ):
            return False
        if command_name not in self.active_onboarding_tasks:
            return False
        if self.bot.hold_command:
            return False
        if command_name in gambling_commands:
            gambling = self.bot.get_cog("Gambling")
            if gambling is not None and gambling.is_busy():
                return False
        cd = self.get_cooldown(command_name)
        if time.time() - self.bot.last_ran[command_name] < cd:
            return False
        return True

    async def _send_command(self, command):
        if command == "dep_all":
            await self.bot.send_cmd(f"{onboarding_commands[command]} all")
            return
        if command == "use cheese":
            # /use item:"shredded cheese" - multi-word item needs explicit kwargs.
            await self._send_use_cheese()
            return
        if command in ("sell", "buy"):
            autobuy = self.bot.get_cog("AutoBuy")
            if autobuy is not None:
                if command == "sell":
                    await autobuy.shop_sell()
                else:
                    await autobuy.shop_buy("shovel", 1)
            return
        if command in gambling_commands:
            await self.bot.send_cmd(onboarding_commands[command])
            gambling = self.bot.get_cog("Gambling")
            if gambling is not None:
                gambling.mark_session_started()
            return
        await self.bot.send_cmd(onboarding_commands[command])

    async def _send_use_cheese(self):
        from discord import SlashCommand

        try:
            commands = await self.bot.channel.application_commands()
        except Exception as e:
            self.bot.log(f"use cheese - failed to fetch commands: {e}", "red")
            return
        use_cmd = next(
            (
                c
                for c in commands
                if isinstance(c, SlashCommand)
                and c.application.id == 270904126974590976
                and c.name.lower() == "use"
            ),
            None,
        )
        if use_cmd is None:
            self.bot.log("use cheese - /use command not found", "red")
            return
        try:
            await use_cmd(channel=self.bot.channel, item="shredded cheese")
            self.bot.log("use cheese - used shredded cheese", "green")
            self.bot.last_ran["use cheese"] = time.time()
        except Exception as e:
            self.bot.log(f"use cheese - failed: {e}", "red")

    @tasks.loop()
    async def onboarding_handler(self):
        try:
            if not self.enabled() or not self.bot.state:
                await asyncio.sleep(0.5)
                return

            # Make sure the gateway is up so slash-interaction responses can
            # actually be received before we rely on them.
            if getattr(self.bot, "ws", None) is None:
                await asyncio.sleep(1)
                return

            # Pull the full onboarding details (current level + task list)
            # via /scratch. Since scratch is still locked on this account, the
            # response is the "not unlocked" message which embeds the level's
            # progress rows and is parsed by _handle_onboarding. Wait for that
            # response before running any task so the stale task set (e.g.
            # previous level's craft/farm) is rebuilt first. Retry every 30s if
            # the response never arrived (e.g. sent before gateway was ready).
            if not self._details_seen:
                now = time.time()
                if now - self._last_scratch_sent > 30:
                    self._last_scratch_sent = now
                    self._details_fetched = True
                    self.bot.last_ran["scratch"] = now
                    try:
                        await self.bot.send_cmd("scratch")
                    except Exception as e:
                        self.bot.log(
                            f"Failed to fetch onboarding details via /scratch: {e}",
                            "red",
                        )
                await asyncio.sleep(3)
                return

            # If the target level has been reached, stop onboarding so the
            # normal commands.py rotation takes over.
            self._maybe_complete()
            if not self.enabled():
                await asyncio.sleep(1)
                return

            self._probe_locked_commands()

            shuffled = list(self.active_onboarding_tasks)[:]
            self.bot.random.shuffle(shuffled)

            for command in shuffled:
                await asyncio.sleep(
                    self.bot.random.uniform(self.minCommandCD, self.maxCommandCD)
                )
                if not self.should_run(command):
                    continue
                self.bot.last_ran[command] = time.time()
                try:
                    await self._send_command(command)
                except Exception as e:
                    self.bot.log(f"Failed to run onboarding '{command}': {e}", "red")
                    continue

            await asyncio.sleep(self.sleep_time)
        except Exception as e:
            self.bot.log(f"onboarding_handler error: {e}", "red")
            await asyncio.sleep(5)

    async def cog_load(self):
        print(
            f"Onboarding cog loaded (enabled={self.enabled()}), "
            f"level={self.current_level}, approx min {self.sleep_time}"
        )
        self.onboarding_handler.start()


async def setup(bot):
    await bot.add_cog(Onboarding(bot))
