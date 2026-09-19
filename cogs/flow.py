import time

import components_v2

from discord.ext import commands, tasks

DANK_MEMER_ID = 270904126974590976

# Labels on Dank Memer's flow UI (all components v2). List/detail screens
# are stable ("View", "Start", "Stop"); the per-step advance label is
# learned from live messages and logged when unknown.
_STEP_LABELS = ("next", "run", "continue", "next command", "run command")
_STOP_LABELS = ("stop", "end flow", "end", "finish")
_SKIP_LABELS = ("skip",)


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

    def _find_label(self, buttons, needles):
        for b in buttons:
            label = (getattr(b, "label", None) or "").lower()
            if any(n in label for n in needles):
                if not getattr(b, "disabled", False):
                    return b
        return None

    def _find_view_accessory(self, message):
        # "View" is a section accessory; pick the section for our flow.
        want = self.flow_name().lower()
        for comp in getattr(message, "components", None) or []:
            if getattr(comp, "component_name", None) != "section":
                continue
            try:
                texts = [
                    c.content or ""
                    for c in comp.components
                    if getattr(c, "component_name", None) == "text_display"
                ]
            except (AttributeError, TypeError):
                continue
            if any(want in t.lower() for t in texts):
                btn = getattr(comp, "accessory", None)
                if (
                    btn is not None
                    and "flow-" in (getattr(btn, "custom_id", None) or "")
                    and not getattr(btn, "disabled", False)
                ):
                    return btn
        return None

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
        if not buttons:
            if joined.strip():
                self.bot.log(f"flow - reply: {joined.strip()[:150]}", "yellow")
            return
        self.last_flow_msg = time.time()
        labels = [(getattr(b, "label", None) or "?") for b in buttons]

        # Graceful exit: flow disabled while active -> press Stop.
        if self.active and not self.enabled():
            stop = self._find_label(buttons, _STOP_LABELS)
            if stop is not None:
                if await self.bot.click_button(stop):
                    self.bot.log("flow - stopped (mode disabled)", "yellow")
                    self.active = False
            return
        if not self.enabled():
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
        stop = self._find_label(buttons, _STOP_LABELS)
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

        # 4. Active flow step: advance to the next command.
        if self.active:
            step = self._find_label(buttons, _STEP_LABELS)
            if step is None:
                # Fallback: the only enabled flow button that isn't
                # stop/skip. Ambiguous screens are logged, not clicked.
                others = [
                    b
                    for b in buttons
                    if not getattr(b, "disabled", False)
                    and (getattr(b, "label", None) or "").lower()
                    not in _STOP_LABELS + _SKIP_LABELS
                ]
                step = others[0] if len(others) == 1 else None
            if step is not None:
                if await self.bot.click_button(step):
                    self.bot.log(
                        f"flow - next ({getattr(step, 'label', None)})", "green"
                    )
                else:
                    self.bot.log(
                        f"flow click failed ({getattr(step, 'label', None)})", "red"
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
            self.bot.log(f"flow - unknown step buttons: {labels}", "red")
            return

        # 5. Not active and no list/start matched: log for learning.
        self.bot.log(f"flow - idle, buttons: {labels} | {joined[:120]}", "yellow")

    @tasks.loop(seconds=30)
    async def flow_driver(self):
        try:
            if not self.enabled() or not self.bot.state:
                return
            if self.bot.hold_command:
                return
            if self.active:
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
