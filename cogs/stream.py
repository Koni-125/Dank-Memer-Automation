import asyncio
import random
import re
import time

import components_v2

from discord.ext import commands

DANK_MEMER_ID = 270904126974590976
_COOLDOWN_RE = re.compile(r"can't interact with your stream[^\"]*?<t:(\d+):R>")


class Stream(commands.Cog):
    """Automate "pls stream".

    Handles both states of the stream embed:
      - "Last Live"  -> not streaming: click Go Live, pick a game, start.
      - "Live Since" -> streaming: click chat/ad/donations from the configured
        `order` list to keep the stream active and earn viewers/xp.

    Dank Memer limits stream interactions to once per ~10 minutes; when it
    replies "You can't interact with your stream right now. Try <t:...:R>" we
    parse the Discord timestamp and pause clicking until it passes.
    """

    def __init__(self, bot):
        self.bot = bot
        stream_config = bot.settings_dict["commands"].get("stream", {})
        self.order = stream_config.get("order", [1, 1, 1, 1, 1, 0, 0, 0, 2, 2, 2])
        # During onboarding the objective is "Attempt to collect ad revenue",
        # so prioritize Run AD (0) and Collect Donations (2) instead of the
        # normal Read Chat rotation.
        self.onboarding_order = stream_config.get(
            "onboarding_order", [0, 0, 0, 2, 2, 2]
        )
        self.click_counter = 0
        self._last_action = 0
        self._last_message_id = None
        self._cooldown_until = 0
        self.bot.message_dispatcher.register(self.log_messages)

    def _onboarding_active(self):
        onboarding = self.bot.get_cog("Onboarding")
        return onboarding is not None and onboarding.enabled()

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return
        # The cooldown reply appears in two forms depending on the button:
        #  - "Read Chat"      -> ephemeral components_v2 text_display
        #  - "Run AD"/others  -> components_v1 embed description
        texts = list(components_v2.message.text_display_contents(message))
        if getattr(message, "embeds", None):
            for embed in message.embeds:
                desc = getattr(embed, "description", None) or ""
                if desc:
                    texts.append(desc)
        for text in texts:
            if "can't interact with your stream" in text:
                match = _COOLDOWN_RE.search(text)
                if match:
                    self._cooldown_until = int(match.group(1))
                    mins = max(1, int((self._cooldown_until - time.time()) // 60))
                    self.bot.log(
                        f"stream - interaction cooldown until "
                        f"<t:{self._cooldown_until}:R> (~{mins}m), waiting...",
                        "yellow",
                    )
                    # Backdate `last_ran` so the configured stream delay
                    # expires exactly when the interaction unlocks. Setting it
                    # to a future timestamp would make the cooldown check
                    # (`now - last_ran < delay`) stay true past the unlock,
                    # causing the bot to over-wait by a whole extra delay.
                    delay = self.bot.settings_dict["commands"]["stream"].get(
                        "delay", 660
                    )
                    self.bot.last_ran["stream"] = self._cooldown_until - delay
                return
    def _stream_state(self, message):
        if message.channel.id != self.bot.channel_id:
            return None
        if message.author.id != DANK_MEMER_ID:
            return None
        if not message.embeds:
            return None
        try:
            fields = message.embeds[0].to_dict().get("fields", [])
        except (KeyError, IndexError, AttributeError):
            return None
        names = [f.get("name", "") for f in fields]
        if "Last Live" in names:
            return "last_live"
        if "Live Since" in names:
            return "live"
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        state = self._stream_state(message)
        if state == "last_live":
            await self._go_live(message)
        elif state == "live":
            await self._read_chat(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # The stream message is a single message that gets edited as the
        # stream progresses, so act on edits as well. Multiple rapid edits fire
        # for one interaction, so throttle clicks to avoid invalidating each
        # other (COMPONENT_VALIDATION_FAILED).
        state = self._stream_state(after)
        if state != "live":
            return
        now = time.time()
        if after.id == self._last_message_id and now - self._last_action < 15:
            return
        await self._read_chat(after)

    def _on_cooldown(self):
        return time.time() < self._cooldown_until

    def _button_label(self, message, index):
        try:
            return message.components[0].children[index].label
        except (IndexError, AttributeError):
            return str(index)

    async def _go_live(self, message):
        if not message.components or not message.components[0].children:
            return
        if self._on_cooldown():
            return
        try:
            await self.bot.set_command_hold_stat(True)

            # 1. Click "Go Live".
            await self.bot.click(message, 0, 0)
            await asyncio.sleep(0.7)

            # 2. Pick a random game from the select menu (row 0 col 0).
            await self.bot.select(message, 0, 0, random.randint(0, 24))
            await asyncio.sleep(0.7)

            # 3. Click the "Go Live" start button (row 1 col 0).
            await self.bot.click(message, 1, 0)
            self.click_counter = 0
            self.bot.last_ran["stream"] = time.time()
            self.bot.log("stream - went live", "green")
        except Exception as e:
            self.bot.log(f"stream - go live failed: {e}", "red")
        finally:
            if self.bot.hold_command:
                await self.bot.set_command_hold_stat(False)

    async def _read_chat(self, message):
        if not message.components or not message.components[0].children:
            return
        if self._on_cooldown():
            return
        # While onboarding is running, satisfy the "collect ad revenue"
        # objective by clicking Run AD / Collect Donations. Only use the normal
        # Read Chat rotation once onboarding is done.
        order = self.onboarding_order if self._onboarding_active() else self.order
        try:
            await self.bot.set_command_hold_stat(True)
            click_value = order[self.click_counter % len(order)]
            await self.bot.click(message, 0, click_value)
            self.click_counter += 1
            self._last_action = time.time()
            self._last_message_id = message.id
            self.bot.last_ran["stream"] = time.time()
            self.bot.log(
                f"stream - clicked '{self._button_label(message, click_value)}'",
                "green",
            )
        except Exception as e:
            self.bot.log(f"stream - read chat failed: {e}", "red")
        finally:
            if self.bot.hold_command:
                await self.bot.set_command_hold_stat(False)


async def setup(bot):
    await bot.add_cog(Stream(bot))
