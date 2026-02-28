import asyncio

from discord.ext import commands


class Tidy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)

        tidy_config = self.bot.settings_dict["commands"]["tidy"]
        preferred_tool = tidy_config.get("tools", tidy_config.get("tool"))
        if isinstance(preferred_tool, str):
            self.priority = [preferred_tool.lower()]
        elif isinstance(preferred_tool, list):
            self.priority = [
                item.lower() for item in preferred_tool if isinstance(item, str)
            ]
        else:
            self.priority = ["hand"]

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if not message.components:
            return

        prompt_found = False
        for component in message.components:
            if component.component_name == "text_display":
                if (
                    isinstance(component.content, str)
                    and "Pick what to tidy up with." in component.content
                ):
                    prompt_found = True
                    break
        if not prompt_found:
            return

        valid_buttons = []
        for button in message.buttons:
            if getattr(button, "label", None):
                valid_buttons.append(button)
        if not valid_buttons:
            return

        by_label = {button.label.lower(): button for button in valid_buttons}

        button = None
        for preferred in self.priority:
            preferred_button = by_label.get(preferred)
            if preferred_button and not getattr(preferred_button, "disabled", False):
                button = preferred_button
                break

        if button is None:
            hand_button = by_label.get("hand")
            if hand_button and not getattr(hand_button, "disabled", False):
                button = hand_button

        if button is None:
            enabled_buttons = []
            for candidate in valid_buttons:
                if not getattr(candidate, "disabled", False):
                    enabled_buttons.append(candidate)
            if enabled_buttons:
                button = self.bot.random.choice(enabled_buttons)

        if button is None:
            return

        await self.bot.set_command_hold_stat(True)
        try:
            await asyncio.sleep(self.bot.random.uniform(0.3, 0.5))
            stat = await button.click(
                self.bot.ws.session_id,
                self.bot.local_headers,
                str(self.bot.channel.guild.id),
            )
            if stat:
                self.bot.log(f"tidy - clicked {button.label}", "green")
            else:
                self.bot.log(f"tidy - failed clicking {button.label}", "red")
        finally:
            if self.bot.hold_command:
                await self.bot.set_command_hold_stat(False)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        prompt_found = False
        if message.embeds and message.embeds[0].description:
            if "Pick what to tidy up with." in message.embeds[0].description:
                prompt_found = True
        if not prompt_found:
            return

        if not message.components:
            return

        valid_buttons = []
        for row in message.components:
            for child in getattr(row, "children", []):
                if getattr(child, "label", None):
                    valid_buttons.append(child)
        if not valid_buttons:
            return

        by_label = {button.label.lower(): button for button in valid_buttons}

        button = None
        for preferred in self.priority:
            preferred_button = by_label.get(preferred)
            if preferred_button and not getattr(preferred_button, "disabled", False):
                button = preferred_button
                break

        if button is None:
            hand_button = by_label.get("hand")
            if hand_button and not getattr(hand_button, "disabled", False):
                button = hand_button

        if button is None:
            enabled_buttons = []
            for candidate in valid_buttons:
                if not getattr(candidate, "disabled", False):
                    enabled_buttons.append(candidate)
            if enabled_buttons:
                button = self.bot.random.choice(enabled_buttons)

        if button is None:
            return

        await button.click()
        self.bot.log(f"tidy - clicked {button.label}", "green")


async def setup(bot):
    await bot.add_cog(Tidy(bot))
