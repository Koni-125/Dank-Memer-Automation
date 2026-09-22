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

# Stuck-flow watchdog: the interaction API sometimes swallows a button
# click with no error, so no MESSAGE_UPDATE arrives and an active flow
# stalls forever. _WATCHDOG_S after the last flow-button click attempt
# with no deliberate wait running, the driver re-pokes the last screen;
# after _WATCHDOG_TRIPS pokes with nothing landing, it ends that flow
# and starts a new one. Spacing keeps pokes >=2min apart; the counter
# decays after _WATCHDOG_DECAY_S so old incidents never stack up.
_WATCHDOG_S = 120
_WATCHDOG_TRIPS = 3
_WATCHDOG_SPACING_S = 120
_WATCHDOG_DECAY_S = 600

# Completion proof: whole-word phrases only. The old substring check
# ("complet" in text) false-fired on postmemes' Discord result
# ("To be completely honest, your meme was kinda mid."), Stop-clicking
# a live 7/8 step and restarting the loop from scratch.
_COMPLETION_RES = (
    re.compile(r"\bcomplete(?:d|s|tion)?\b", re.IGNORECASE),
    re.compile(r"\bfinish(?:ed|es)?\b", re.IGNORECASE),
    re.compile(r"\ball commands\b", re.IGNORECASE),
    re.compile(r"\bflow ended\b", re.IGNORECASE),
    re.compile(r"\bwell done\b", re.IGNORECASE),
)


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
        self.last_flow_msg_id = 0
        # Watchdog feed: last flow-button click ATTEMPT (hook in
        # MyClient.click_button stamps these). Attempt, not success --
        # swallowed clicks report no error, so "tried" is the signal.
        self.last_click_at = 0
        self._watchdog_trips = 0
        self._watchdog_last_at = 0
        self._skip_sightings = {}
        self._structure_logged = False
        # Breaks are owned by commands.py on shared bot flags
        # (break_requested / on_break / break_until); this cog only
        # obeys them. _saw_break edge-triggers the post-rest resume.
        self._saw_break = False
        self._backoff_until = 0
        self._step_wait_until = 0
        self._step_wait_key = None
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

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

    # -- screen predicates (no clicks here) -------------------------------

    def _screen_has_enabled(self, buttons, needles):
        return self._find_label(buttons, needles) is not None

    @staticmethod
    def _parse_progress(joined):
        # Progress footer ("-# 7/8 | **postmemes** -> ..."): (done, total).
        # (None, None) when no footer is present.
        try:
            match = re.search(r"(\d+)\s*/\s*(\d+)", joined or "")
            if not match:
                return None, None
            return int(match.group(1)), int(match.group(2))
        except (TypeError, ValueError):
            return None, None

    def _is_completion_screen(self, joined, buttons, stop):
        # ALL of these must hold before we touch Stop for "finished":
        #   1. a Stop control exists,
        #   2. no enabled Continue/Start is present (a live step screen),
        #   3. the progress footer (when shown) reads done >= total,
        #   4. a whole-word completion phrase is in the text.
        # Rule 4 alone caused the 13:16 incident: postmemes' Discord result
        # ("To be completely honest, your meme was kinda mid.") contains
        # "complet" as a substring of "completely" at 7/8 with Continue
        # enabled -- Stop got clicked mid-flow and the loop restarted.
        if stop is None:
            return False
        if self._screen_has_enabled(buttons, _STEP_LABELS + ("start",)):
            return False
        done, total = self._parse_progress(joined)
        if total and done is not None and done < total:
            return False
        try:
            text = (joined or "").lower()
        except Exception:
            return False
        return any(rx.search(text) for rx in _COMPLETION_RES)

    # -- _handle stages (each does one job, True = handled, stop here) ----

    def _gate_message(self, message):
        # Channel + ownership + rest-state gates. False = ignore silently.
        try:
            if message.channel_id != self.bot.channel.id:
                return False
        except AttributeError:
            return False
        if not self._is_ours(message):
            return False
        # Resting on the shared schedule: fully deaf. Ignored screens
        # must not refresh last_flow_msg, or the driver's 90s silence
        # gate delays the post-break /flow re-request.
        if getattr(self.bot, "on_break", False):
            return False
        return True

    def _collect_screen(self, message):
        # Pull text, flow buttons and section accessories off the message.
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
        buttons = self._flow_buttons(message)
        accessories = self._section_accessories(message)
        return {
            "message": message,
            "joined": joined,
            "buttons": buttons,
            "accessories": accessories,
            "labels": [(getattr(b, "label", None) or "?") for b in buttons],
            "acc_labels": [
                (getattr(b, "label", None) or "?") for b in accessories
            ],
            "step_key": self._parse_step_key(joined),
        }

    def _note_flow_reply(self, screen):
        # Track ANY of Dank Memer's replies to our flow interaction (even
        # errors like "That flow does not exist.") so the driver backs off
        # instead of re-sending every 30s.
        if "flow" in screen["joined"].lower():
            self.last_flow_msg = time.time()

    def _refresh_step_wait(self, screen):
        # A new step means any old cooldown wait no longer applies. Only
        # reset on a real header: headerless updates mid-wait must not
        # clear it early.
        step_key = screen["step_key"]
        if step_key is not None and step_key != self._step_wait_key:
            self._step_wait_until = 0
            self._step_wait_key = None

    async def _handle_graceful_stop(self, screen):
        # Graceful exit: flow disabled -> Stop and go idle; shared break
        # requested (the single schedule lives in commands.py) -> Stop
        # and start the scheduled rest on the shared flags.
        # Stop is a section accessory (never in message.buttons), so use
        # _find_stop which checks both. Loud when missing so a stall is
        # visible instead of a mystery.
        want_rest = bool(getattr(self.bot, "break_requested", False))
        if not (self.active and (not self.enabled() or want_rest)):
            return False
        stop = self._find_stop(screen["message"], screen["buttons"])
        if stop is not None:
            if await self.bot.click_button(stop):
                if want_rest:
                    self.bot.break_requested = False
                    self.bot.on_break = True
                    try:
                        mins = int((self.bot.break_until - time.time()) // 60)
                    except (TypeError, AttributeError):
                        mins = 0
                    self.bot.log(
                        f"flow - stopped, resting ~{max(mins, 1)}m", "yellow"
                    )
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
                f"(buttons={screen['labels']} accessories={screen['acc_labels']})",
                "yellow",
            )
        return True

    async def _handle_backoff(self, screen):
        # Rate-limit notices (_backoff equivalent): Hold Tight / command
        # in progress / Too spicy. Pause Continue clicks for a bit.
        if not self.active:
            return False
        if any(t in screen["joined"] for t in _BACKOFF_TEXTS):
            self._backoff_until = time.time() + _BACKOFF_S
            self.bot.log(
                f"flow - rate limited, backing off {_BACKOFF_S}s", "yellow"
            )
            return True
        if time.time() < self._backoff_until:
            return True
        return False

    async def _handle_flow_list(self, screen):
        # Flow list ("### Flows"): open the configured flow.
        joined = screen["joined"]
        if (
            "### Flows" not in joined
            and "grind easier with flow" not in joined.lower()
        ):
            return False
        view = self._find_view_accessory(screen["message"])
        if view is not None:
            self.bot.log(f"flow - opening '{self.flow_name()}'", "green")
            await self.bot.click_button(view)
        else:
            self.bot.log(
                f"flow - '{self.flow_name()}' not found in list", "red"
            )
        return True

    async def _handle_completion(self, screen):
        # End of flow: Stop + completion proof -> click Stop once.
        # Never fires on a live step screen (Continue/Start enabled,
        # footer behind total, or no whole-word completion phrase).
        stop = self._find_stop(screen["message"], screen["buttons"])
        if stop is None:
            return False
        if not self._is_completion_screen(
            screen["joined"], screen["buttons"], stop
        ):
            return False
        if not self.active:
            self.bot.log("flow - completion screen while idle, ignoring", "yellow")
            return True
        if await self.bot.click_button(stop):
            self.bot.log("flow - finished, stopped", "green")
            self.active = False
        else:
            self.bot.log("flow - Stop click failed, retrying", "red")
        return True

    async def _handle_start(self, screen):
        # Start button -> flow becomes active.
        start = self._find_label(screen["buttons"], ("start",))
        if start is None or self.active:
            return False
        if await self.bot.click_button(start):
            self.bot.log(f"flow - started '{self.flow_name()}'", "green")
            self.active = True
        return True

    async def _handle_idle(self, screen):
        # Resume screen: Continue with no game pending while idle
        # (e.g. re-attaching to a flow left active by a previous session).
        # Otherwise log for learning.
        pending = self._game_pending(screen["buttons"])
        if pending:
            self.bot.log(
                "flow - idle with game pending, waiting: "
                + str([(getattr(b, "label", None) or "?") for b in pending]),
                "yellow",
            )
            return
        resume = self._find_label(screen["buttons"], _STEP_LABELS)
        if resume is not None:
            if await self.bot.click_button(resume):
                self.bot.log(f"flow - resumed '{self.flow_name()}'", "green")
                self.active = True
            return
        # Not active and no list/start matched: log for learning.
        self.bot.log(
            f"flow - idle, buttons: {screen['labels'] + screen['acc_labels']} "
            f"| {screen['joined'][:120]}",
            "yellow",
        )

    async def _click_step(self, screen):
        step = self._find_label(screen["buttons"], _STEP_LABELS)
        if step is None:
            return False
        if await self.bot.click_button(step):
            self.bot.log(
                f"flow - next ({getattr(step, 'label', None)})", "green"
            )
            # The step's command just fired: stamp last_ran now so
            # the NEXT loop's cooldown wait has a real timestamp.
            self._mark_step_ran(screen["step_key"])
            self._step_wait_until = 0
            self._step_wait_key = None
        else:
            self.bot.log(
                f"flow click failed ({getattr(step, 'label', None)})", "red"
            )
        return True

    async def _park_for_cooldown(self, screen):
        parked = self._find_label(screen["buttons"], _STEP_LABELS, only_enabled=False)
        if parked is None:
            return False
        # Continue exists but is disabled: the step's command is
        # on cooldown. Wait it out per shared last_ran (set when
        # the step last fired) -- do NOT fall through to Skip.
        # Re-check when the wait expires; the button should enable.
        wait = self._cooldown_wait_s(screen["step_key"])
        self._step_wait_until = time.time() + wait
        self._step_wait_key = screen["step_key"]
        self.bot.log(
            f"flow - Continue disabled ({screen['step_key'] or '?'}), "
            f"cooling down ~{wait}s",
            "yellow",
        )
        return True

    async def _nudge_stuck_skip(self, screen):
        skip = self._find_label(screen["buttons"], _SKIP_LABELS)
        if skip is None:
            self.bot.log(
                f"flow - unknown step buttons: {screen['labels'] + screen['acc_labels']}",
                "red",
            )
            return
        mid = getattr(screen["message"], "id", 0)
        n = self._skip_sightings.get(mid, 0) + 1
        self._skip_sightings[mid] = n
        if len(self._skip_sightings) > 50:
            self._skip_sightings.pop(next(iter(self._skip_sightings)))
        self.bot.log(f"flow - only Skip available (x{n}), waiting", "yellow")
        if n >= 4:
            if await self.bot.click_button(skip):
                self.bot.log("flow - skipped stuck step", "yellow")
            self._skip_sightings.pop(mid, None)

    async def _handle_active_step(self, screen):
        # Active flow step: advance to the next command. Game-choice
        # buttons (e.g. search locations) belong to the game cogs, which
        # run later in the same dispatch pass -- if any non-navigation
        # flow button is present, wait for them instead of Continuing.
        pending = self._game_pending(screen["buttons"])
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
        if await self._click_step(screen):
            return
        if await self._park_for_cooldown(screen):
            return
        await self._nudge_stuck_skip(screen)

    def note_flow_click(self):
        # Stamped by the MyClient.click_button hook on every flow-button
        # click attempt (flow cog + game cogs alike). Resets the watchdog:
        # something moved, so the flow is not stalled.
        self.last_click_at = time.time()
        self._watchdog_trips = 0

    # -- stuck-flow watchdog (each does one job) --------------------------

    def _watchdog_due(self, now):
        # Pure gate: True only while grinding (never on a break), the
        # flow owned-and-active, and nothing clicked or deliberately
        # waited on for a while. Cooldown parking and rate-limit
        # backoff are quiet ON PURPOSE -- never mistake those for stuck.
        try:
            if not self.enabled() or not self.active:
                return False
        except Exception:
            return False
        if getattr(self.bot, "on_break", False) or getattr(
            self.bot, "break_requested", False
        ):
            return False
        try:
            if not self.bot.state or self.bot.hold_command:
                return False
        except (AttributeError, TypeError):
            return False
        if not self.last_click_at or not self.last_flow_msg_id:
            return False
        if now - self.last_click_at < _WATCHDOG_S:
            return False
        if now - self._watchdog_last_at < _WATCHDOG_SPACING_S:
            return False
        if now < self._step_wait_until or now < self._backoff_until:
            return False
        return True

    def _watchdog_rebuild_screen(self):
        # Rebuild the last live screen from the gateway cache -- the same
        # merge pipeline on_socket_raw_receive uses, so the object shape
        # is exactly what _handle expects. No network fetch involved.
        # Cache keys are raw string ids while message.id is int: try both.
        try:
            cache = getattr(self.bot, "_raw_message_cache", None) or {}
            raw = cache.get(self.last_flow_msg_id)
            if raw is None:
                raw = cache.get(str(self.last_flow_msg_id))
            if not raw:
                return None
            return components_v2.message.get_message_obj(raw)
        except Exception:
            return None

    async def _watchdog_redispatch(self, message):
        # Poke the stalled screen back through the normal dispatcher, as
        # if Dank had re-sent the update: the flow stages AND the game
        # cogs all see it again and can re-click. Any click that lands
        # resets the trip counter via note_flow_click.
        try:
            await self.bot.message_dispatcher.dispatch_on_edit(message)
            return True
        except Exception as e:
            self.bot.log(f"flow - watchdog redispatch failed: {e}", "red")
            return False

    async def _watchdog_restart(self):
        # Give up on the stalled screen: Stop it if a Stop control is
        # still there, forget it, and let the driver request a fresh
        # /flow list (which starts a new flow) on its next tick.
        try:
            rebuilt = self._watchdog_rebuild_screen()
            if rebuilt is not None:
                screen = self._collect_screen(rebuilt)
                stop = self._find_stop(screen["message"], screen["buttons"])
                if stop is not None:
                    await self.bot.click_button(stop)
        except Exception:
            pass
        self.active = False
        self.last_flow_msg = 0
        self.last_flow_msg_id = 0
        self._step_wait_until = 0
        self._step_wait_key = None
        self._watchdog_trips = 0
        self.bot.log("flow - watchdog: ended stalled flow, starting a new one", "yellow")

    async def _maybe_watchdog_recover(self):
        # Called from the driver while the flow is active (never while
        # stopping for / on a break). Re-pokes the last screen after
        # _WATCHDOG_S of click silence; after _WATCHDOG_TRIPS pokes with
        # nothing landing, ends that flow and starts a new one.
        now = time.time()
        if not self._watchdog_due(now):
            return False
        if now - self._watchdog_last_at > _WATCHDOG_DECAY_S:
            self._watchdog_trips = 0
        self._watchdog_trips += 1
        self._watchdog_last_at = now
        idle_s = int(now - self.last_click_at)
        if self._watchdog_trips >= _WATCHDOG_TRIPS:
            self.bot.log(
                f"flow - watchdog: no click for {idle_s}s "
                f"({_WATCHDOG_TRIPS} tries), restarting flow",
                "yellow",
            )
            await self._watchdog_restart()
            return True
        rebuilt = self._watchdog_rebuild_screen()
        if rebuilt is None:
            self.bot.log(
                "flow - watchdog: last screen gone from cache, restarting flow",
                "yellow",
            )
            await self._watchdog_restart()
            return True
        self.bot.log(
            f"flow - watchdog: no click for {idle_s}s, re-poking last screen",
            "yellow",
        )
        await self._watchdog_redispatch(rebuilt)
        return True

    async def _handle(self, message):
        # Thin orchestrator: gate, collect, then one stage at a time.
        # Each stage returns True when it handled the screen.
        if not self._gate_message(message):
            return
        screen = self._collect_screen(message)
        self._note_flow_reply(screen)
        if not screen["buttons"] and not screen["accessories"]:
            if screen["joined"].strip():
                self.bot.log(
                    f"flow - reply: {screen['joined'].strip()[:150]}", "yellow"
                )
            return
        self.last_flow_msg = time.time()
        try:
            self.last_flow_msg_id = int(getattr(screen["message"], "id", 0) or 0)
        except (TypeError, ValueError):
            pass
        self._refresh_step_wait(screen)
        if await self._handle_graceful_stop(screen):
            return
        if not self.enabled():
            return
        # Stopping for the scheduled break: freeze everything except the
        # Stop click above. Advancing (Continue/Start/View) while trying
        # to stop just keeps the flow alive.
        if getattr(self.bot, "break_requested", False):
            return
        if await self._handle_backoff(screen):
            return
        if await self._handle_flow_list(screen):
            return
        if await self._handle_completion(screen):
            return
        if await self._handle_start(screen):
            return
        if not self.active:
            await self._handle_idle(screen)
            return
        await self._handle_active_step(screen)

    @tasks.loop(seconds=30)
    async def flow_driver(self):
        try:
            if not self.enabled():
                self._saw_break = False
                return
            if not self.bot.state:
                return
            if self.bot.hold_command:
                return
            now = time.time()
            # Breaks are scheduled by commands.py on shared bot flags;
            # this driver only obeys them (it schedules nothing itself).
            if getattr(self.bot, "on_break", False):
                self._saw_break = True
                return
            if self._saw_break:
                # Rest just ended (scheduler already logged it): resume
                # silently and force the /flow re-request -- screens seen
                # during the rest were ignored, so last_flow_msg would
                # otherwise hold off the 90s silence gate.
                self._saw_break = False
                self.last_flow_msg = 0
            # Asked to Stop for the scheduled break but no screen to
            # stop on: rest anyway rather than stalling the schedule;
            # the driver re-attaches with View after the rest.
            if getattr(self.bot, "break_requested", False) and (
                now - self.last_flow_msg > 300
            ):
                self.bot.log("flow - no screen to stop on, resting anyway", "yellow")
                self.active = False
                self.bot.break_requested = False
                self.bot.on_break = True
                return
            if getattr(self.bot, "break_requested", False) or self.active:
                # Stuck-flow watchdog: a swallowed click raises no error
                # and delivers no update, so _handle never re-fires and an
                # active flow stalls forever (the 90s silence gate below
                # only acts while idle). Never runs while stopping for or
                # resting on a break -- _watchdog_due gates that.
                if self.active and not getattr(self.bot, "break_requested", False):
                    await self._maybe_watchdog_recover()
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
