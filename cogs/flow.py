import random
import re
import time

import components_v2

from discord.ext import commands, tasks

from cogs.commands import commands_min_cd

DANK_MEMER_ID = 270904126974590976

# Labels on Dank Memer's flow UI (all components v2). List/detail screens
# are stable ("View", "Start", "Stop"); the per-step advance label is
# learned from live messages and logged when unknown.
_STEP_LABELS = ("next", "run", "continue", "next command", "run command")
_STOP_LABELS = ("stop", "end flow", "end", "finish")
_SKIP_LABELS = ("skip",)

# Displayed step names in the progress header ("**search** -> dig ...")
# mapped to rotation keys for last_ran tracking.
_STEP_TO_KEY = {"postmemes": "pm", "highlow": "hl"}

# Rate-limit/cooldown notices: pause Continue clicks for _BACKOFF_S.
_BACKOFF_S = 30
_BACKOFF_TEXTS = ("already have a command in progress", "Too spicy", "Hold Tight")


class Flow(commands.Cog):
    """Drive Dank Memer's /flow UI instead of sending prefix commands.

    Sequence: /flow list -> View (configured flow) -> Start -> click the
    step button for each command -> Stop when the flow ends. While this
    cog is enabled the normal rotation loop in commands.py pauses so the
    two drivers never clash.
    """

    def __init__(self, bot):
        self.bot = bot
        self.active = False
        self.last_flow_msg = 0
        self._skip_sightings = {}
        self._structure_logged = False
        # Breaks mirror the rotation loop's schedule so flow mode rests
        # the same way. _want_stop ends the flow first (Stop button);
        # _breaking holds the driver until _break_until.
        self._want_stop = False
        self._breaking = False
        self._break_until = 0
        self._backoff_until = 0
        self._step_wait_until = 0
        self._step_wait_key = None
        self.next_break_at = time.time() + random.uniform(
            self._cd("minBreakCooldown", 3600), self._cd("maxBreakCooldown", 10800)
        )
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

    def _cd(self, key, default):
        try:
            return self.bot.settings_dict["settings"]["cooldowns"].get(key, default)
        except (KeyError, TypeError, AttributeError):
            return default

    def _breaks_enabled(self):
        try:
            return bool(self.bot.settings_dict["settings"].get("breaks", False))
        except (AttributeError, TypeError):
            return False

    def _cfg(self):
        try:
            return self.bot.settings_dict["settings"].get("flow", {}) or {}
        except (KeyError, TypeError, AttributeError):
            return {}

    def enabled(self):
        try:
            return bool(self._cfg().get("enabled", False))
        except (AttributeError, TypeError):
            return False

    def flow_name(self):
        try:
            return str(self._cfg().get("flow_name", "Basic Grinding"))
        except (AttributeError, TypeError):
            return "Basic Grinding"

    def refresh_settings(self):
        # All config is read live via _cfg(); nothing cached.
        pass

    def rotation_paused(self):
        # While flow mode owns the loop, commands.py must stay out.
        return self.enabled()

    def should_accept(self, message):
        # Flow-fired command results don't reference our "pls" sends, so
        # the normal ownership check drops them. While a flow is active,
        # accept Dank Memer's channel messages so game cogs still fire.
        try:
            return bool(self.active) and getattr(
                getattr(message, "author", None), "id", None
            ) == DANK_MEMER_ID
        except Exception:
            return False

    async def cog_load(self):
        self.flow_driver.start()

    async def log_messages(self, message):
        try:
            await self._handle(message)
        except Exception as e:
            self.bot.log(f"flow handler error: {e}", "red")

    async def log_messages_edit(self, message):
        try:
            await self._handle(message)
        except Exception as e:
            self.bot.log(f"flow edit handler error: {e}", "red")

    def _is_ours(self, message):
        try:
            if getattr(getattr(message, "author", None), "id", None) != DANK_MEMER_ID:
                return False
            if getattr(message, "interaction_user_id", None) == self.bot.user.id:
                return True
            # Step messages fired by our button clicks may not carry
            # interaction metadata; while active, trust Dank Memer here.
            return bool(self.active)
        except Exception:
            return False

    @staticmethod
    def _flow_buttons(message):
        return [
            b
            for b in (getattr(message, "buttons", None) or [])
            if "flow-" in (getattr(b, "custom_id", None) or "")
        ]

    def _find_label(self, buttons, needles, only_enabled=True):
        for b in buttons:
            label = (getattr(b, "label", None) or "").lower()
            if any(n in label for n in needles):
                if only_enabled and getattr(b, "disabled", False):
                    continue
                return b
        return None

    def _cooldown_wait_s(self, key):
        # How long until this step's command is off cooldown, from the
        # shared last_ran dict (same object commands.py uses). last_ran
        # is only set when the step fires, so this is the previous loop's
        # timestamp. Floor 5s, cap 300s so a stale entry can't stall us.
        try:
            if key:
                last = self.bot.last_ran.get(key, 0)
                min_cd = commands_min_cd.get(key, 30)
                remaining = int(last + min_cd - time.time())
                if remaining > 0:
                    return max(5, min(300, remaining))
                return 5
        except Exception:
            pass
        return 30

    def _section_accessories(self, message):
        # Section accessories (View, Stop) never land in message.buttons:
        # walker() drops section accessories instead of propagating them,
        # so collect them here. Only flow buttons (flow- in custom_id).
        found = []
        try:
            comps = getattr(message, "components", None) or []
        except Exception:
            return found
        # Sections may sit inside containers, so walk one level deep.
        stack = list(comps)
        while stack:
            comp = stack.pop(0)
            try:
                if getattr(comp, "component_name", None) == "section":
                    btn = getattr(comp, "accessory", None)
                    if (
                        btn is not None
                        and "flow-" in (getattr(btn, "custom_id", None) or "")
                    ):
                        found.append(btn)
                    for child in getattr(comp, "components", None) or []:
                        stack.append(child)
                    continue
                for child in getattr(comp, "components", None) or []:
                    stack.append(child)
            except Exception:
                continue
        return found

    def _game_pending(self, buttons):
        # Non-navigation enabled buttons belong to the game cogs (search
        # locations, crime choices...), which run later in the same
        # dispatch pass -- if any are present, wait for them.
        nav = _STEP_LABELS + _SKIP_LABELS + _STOP_LABELS
        return [
            b
            for b in buttons
            if not getattr(b, "disabled", False)
            and not any(n in (getattr(b, "label", None) or "").lower() for n in nav)
        ]

    def _find_stop(self, message, buttons):
        # Stop lives as a section accessory, NOT in message.buttons.
        return self._find_label(
            buttons + self._section_accessories(message), _STOP_LABELS
        )

    def _find_view_accessory(self, message):
        # "View" is a section accessory; pick the section for our flow.
        # Sections may sit inside containers, so walk nested levels.
        want = self.flow_name().lower()
        stack = list(getattr(message, "components", None) or [])
        while stack:
            comp = stack.pop(0)
            try:
                if getattr(comp, "component_name", None) == "section":
                    try:
                        texts = [
                            c.content or ""
                            for c in comp.components
                            if getattr(c, "component_name", None) == "text_display"
                        ]
                    except (AttributeError, TypeError):
                        texts = []
                    if any(want in t.lower() for t in texts):
                        btn = getattr(comp, "accessory", None)
                        if (
                            btn is not None
                            and "flow-" in (getattr(btn, "custom_id", None) or "")
                            and not getattr(btn, "disabled", False)
                        ):
                            return btn
                for child in getattr(comp, "components", None) or []:
                    stack.append(child)
            except Exception:
                continue
        return None

    def _parse_step_key(self, joined):
        # Bold name in the progress header ("-# 2/8 | **search** -> ...")
        # is the CURRENT step; map display name to rotation key.
        try:
            match = re.search(r"\d/\d\s*\|?\s*\*\*(\w+)\*\*", joined)
            if not match:
                return None
            name = match.group(1).lower()
            return _STEP_TO_KEY.get(name, name)
        except Exception:
            return None

    def _mark_step_ran(self, key):
        # Shared last_ran dict (same object commands.py uses). Set only
        # when the step actually fires (Continue clicked), never on sight,
        # so cooldown math uses the previous loop's timestamp.
        try:
            if key and key in self.bot.commands_dict and key in self.bot.last_ran:
                self.bot.last_ran[key] = time.time()
        except Exception:
            pass

    def _start_break(self):
        duration = random.uniform(
            self._cd("minBreakDuration", 1800), self._cd("maxBreakDuration", 18000)
        )
        self._want_stop = False
        self._breaking = True
        self._break_until = time.time() + duration
        self.bot.log(f"flow - taking a break for {int(duration // 60)}m...", "yellow")

    def _maybe_start_break(self):
        if (
            self._breaking
            or self._want_stop
            or not self._breaks_enabled()
            or time.time() < self.next_break_at
        ):
            return
        if not self.active:
            # Nothing running: rest immediately, no Stop dance needed.
            self.bot.log("flow - break due, no active flow", "yellow")
            self._start_break()
            return
        self._want_stop = True
        self.bot.log("flow - break due, stopping flow first", "yellow")

    async def _handle(self, message):
        try:
            if message.channel_id != self.bot.channel.id:
                return
        except AttributeError:
            return
        if not self._is_ours(message):
            return
        texts = components_v2.message.text_display_contents(message) or []
        try:
            embeds = [
                (getattr(e, "title", None) or "")
                + "\n"
                + (getattr(e, "description", None) or "")
                for e in (getattr(message, "embeds", None) or [])
            ]
        except Exception:
            embeds = []
        joined = "\n".join(texts + embeds)
        # Track ANY of Dank Memer's replies to our flow interaction (even
        # errors like "That flow does not exist.") so the driver backs off
        # instead of re-sending every 30s.
        if "flow" in joined.lower():
            self.last_flow_msg = time.time()
        buttons = self._flow_buttons(message)
        accessories = self._section_accessories(message)
        if not buttons and not accessories:
            if joined.strip():
                self.bot.log(f"flow - reply: {joined.strip()[:150]}", "yellow")
            return
        self.last_flow_msg = time.time()
        labels = [(getattr(b, "label", None) or "?") for b in buttons]
        acc_labels = [(getattr(b, "label", None) or "?") for b in accessories]
        step_key = self._parse_step_key(joined)
        # A new step means any old cooldown wait no longer applies. Only
        # reset on a real header: headerless updates mid-wait must not
        # clear it early.
        if step_key is not None and step_key != self._step_wait_key:
            self._step_wait_until = 0
            self._step_wait_key = None

        # Graceful exit: flow disabled OR break due while active -> Stop.
        # Stop is a section accessory (never in message.buttons), so use
        # _find_stop which checks both. Loud when missing so a stall is
        # visible instead of a mystery.
        if self.active and (not self.enabled() or self._want_stop):
            stop = self._find_stop(message, buttons)
            if stop is not None:
                if await self.bot.click_button(stop):
                    if self._want_stop:
                        self._start_break()
                    else:
                        self.bot.log("flow - stopped (mode disabled)", "yellow")
                    self.active = False
                    self._step_wait_until = 0
                    self._step_wait_key = None
                else:
                    self.bot.log("flow - Stop click failed, retrying", "red")
            else:
                self.bot.log(
                    f"flow - want stop, no Stop found "
                    f"(buttons={labels} accessories={acc_labels})",
                    "yellow",
                )
            return
        if not self.enabled():
            return
        # Resting: ignore all flow screens so the list screen can't
        # re-open the flow via View mid-break.
        if self._breaking:
            return

        # Stopping for a break: freeze everything except the Stop click
        # above. Advancing (Continue/Start/View) while trying to stop
        # just keeps the flow alive.
        if self._want_stop:
            return

        # Rate-limit notices (_backoff equivalent): Hold Tight / command
        # in progress / Too spicy. Pause Continue clicks for a bit.
        if self.active and any(t in joined for t in _BACKOFF_TEXTS):
            self._backoff_until = time.time() + _BACKOFF_S
            self.bot.log(
                f"flow - rate limited, backing off {_BACKOFF_S}s", "yellow"
            )
            return
        if self.active and time.time() < self._backoff_until:
            return

        # 1. Flow list ("### Flows"): open the configured flow.
        if "### Flows" in joined or "grind easier with flow" in joined.lower():
            view = self._find_view_accessory(message)
            if view is not None:
                self.bot.log(f"flow - opening '{self.flow_name()}'", "green")
                await self.bot.click_button(view)
            else:
                self.bot.log(
                    f"flow - '{self.flow_name()}' not found in list", "red"
                )
            return

        # 2. Completion text + Stop -> end of flow.
        stop = self._find_stop(message, buttons)
        if stop is not None and any(
            k in joined.lower()
            for k in ("complet", "finish", "all commands", "flow ended", "well done")
        ):
            if await self.bot.click_button(stop):
                self.bot.log("flow - finished, stopped", "green")
                self.active = False
            return

        # 3. Start button -> flow becomes active.
        start = self._find_label(buttons, ("start",))
        if start is not None and not self.active:
            if await self.bot.click_button(start):
                self.bot.log(f"flow - started '{self.flow_name()}'", "green")
                self.active = True
            return

        # 3b. Resume screen: Continue with no game pending while idle
        # (e.g. re-attaching to a flow left active by a previous session).
        if not self.active:
            pending = self._game_pending(buttons)
            if pending:
                self.bot.log(
                    "flow - idle with game pending, waiting: "
                    + str([(getattr(b, "label", None) or "?") for b in pending]),
                    "yellow",
                )
                return
            resume = self._find_label(buttons, _STEP_LABELS)
            if resume is not None:
                if await self.bot.click_button(resume):
                    self.bot.log(f"flow - resumed '{self.flow_name()}'", "green")
                    self.active = True
                return

        # 4. Active flow step: advance to the next command. Game-choice
        # buttons (e.g. search locations) belong to the game cogs, which
        # run later in the same dispatch pass -- if any non-navigation
        # flow button is present, wait for them instead of Continuing.
        if self.active:
            pending = self._game_pending(buttons)
            if pending:
                self.bot.log(
                    "flow - waiting for game: "
                    + str([(getattr(b, "label", None) or "?") for b in pending]),
                    "yellow",
                )
                return
            if time.time() < self._step_wait_until:
                # Cooling down for a disabled Continue; fresh updates
                # still arrive and re-enter here when it enables.
                return
            step = self._find_label(buttons, _STEP_LABELS)
            if step is not None:
                if await self.bot.click_button(step):
                    self.bot.log(
                        f"flow - next ({getattr(step, 'label', None)})", "green"
                    )
                    # The step's command just fired: stamp last_ran now so
                    # the NEXT loop's cooldown wait has a real timestamp.
                    self._mark_step_ran(step_key)
                    self._step_wait_until = 0
                    self._step_wait_key = None
                else:
                    self.bot.log(
                        f"flow click failed ({getattr(step, 'label', None)})", "red"
                    )
                return
            parked = self._find_label(buttons, _STEP_LABELS, only_enabled=False)
            if parked is not None:
                # Continue exists but is disabled: the step's command is
                # on cooldown. Wait it out per shared last_ran (set when
                # the step last fired) -- do NOT fall through to Skip.
                # Re-check when the wait expires; the button should enable.
                wait = self._cooldown_wait_s(step_key)
                self._step_wait_until = time.time() + wait
                self._step_wait_key = step_key
                self.bot.log(
                    f"flow - Continue disabled ({step_key or '?'}), "
                    f"cooling down ~{wait}s",
                    "yellow",
                )
                return
            skip = self._find_label(buttons, _SKIP_LABELS)
            if skip is not None:
                mid = getattr(message, "id", 0)
                n = self._skip_sightings.get(mid, 0) + 1
                self._skip_sightings[mid] = n
                if len(self._skip_sightings) > 50:
                    self._skip_sightings.pop(next(iter(self._skip_sightings)))
                self.bot.log(f"flow - only Skip available (x{n}), waiting", "yellow")
                if n >= 4:
                    if await self.bot.click_button(skip):
                        self.bot.log("flow - skipped stuck step", "yellow")
                    self._skip_sightings.pop(mid, None)
                return
            self.bot.log(
                f"flow - unknown step buttons: {labels + acc_labels}", "red"
            )
            return

        # 5. Not active and no list/start matched: log for learning.
        self.bot.log(
            f"flow - idle, buttons: {labels + acc_labels} | {joined[:120]}",
            "yellow",
        )

    @tasks.loop(seconds=30)
    async def flow_driver(self):
        try:
            if not self.enabled():
                self._want_stop = False
                self._breaking = False
                return
            if not self.bot.state:
                return
            # Schedule breaks before the hold gate: transient click holds
            # (0.5-1.5s around every Continue/game click) must not push the
            # due check past its window tick after tick. The Stop click
            # itself happens in _handle on the next flow screen.
            self._maybe_start_break()
            # No flow message for a while while waiting to stop: give up
            # on the Stop click and rest anyway; View re-attaches later.
            if self._want_stop and time.time() - self.last_flow_msg > 300:
                self.bot.log("flow - no screen to stop on, resting anyway", "yellow")
                self.active = False
                self._start_break()
                return
            if self._breaking:
                if time.time() >= self._break_until:
                    self._breaking = False
                    self.bot.log("flow - break over, resuming", "green")
                    self.next_break_at = time.time() + random.uniform(
                        self._cd("minBreakCooldown", 3600),
                        self._cd("maxBreakCooldown", 10800),
                    )
                return
            if self.bot.hold_command:
                return
            if self._want_stop or self.active:
                return
            if time.time() - self.last_flow_msg < 90:
                return
            if not self._structure_logged:
                self._structure_logged = True
                try:
                    from discord import SlashCommand

                    cmds = await self.bot.channel.application_commands()
                    for c in cmds:
                        if (
                            getattr(getattr(c, "application", None), "id", None)
                            != DANK_MEMER_ID
                            or not isinstance(c, SlashCommand)
                        ):
                            continue
                        if c.name.lower() == "flow":
                            self.bot.log(
                                "flow - cmd children: "
                                + str([ch.name for ch in (c.children or [])])
                                + " options: "
                                + str([o.name for o in (c.options or [])]),
                                "yellow",
                            )
                except Exception as e:
                    self.bot.log(f"flow - structure probe failed: {e}", "red")
            self.bot.log("flow - requesting flow list", "green")
            # /flow takes a single optional 'flow' name option (no
            # subcommands in the fetched command data). Invoking it bare
            # renders the flow list; passing a name tries to run it, so
            # never fill the option with e.g. "list".
            await self.bot.send_slash(["flow"])
        except Exception as e:
            self.bot.log(f"flow driver error: {e}", "red")


async def setup(bot):
    await bot.add_cog(Flow(bot))
