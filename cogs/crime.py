import components_v2

from discord.ext import commands


class Crime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        crime_config = self.bot.settings_dict["commands"]["crime"]

        self.priority = crime_config["priority"]
        self.second_priority = crime_config["second_priority"]
        self.avoid = crime_config["avoid"]
        self.bot.message_dispatcher.register(self.log_messages)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)

    def _pick(self, buttons):
        # buttons: list of clickable v2 accessory buttons.
        shuffled = list(buttons)
        self.bot.random.shuffle(shuffled)
        for button in shuffled:
            if (button.label or "").lower() in self.priority:
                return button
        for button in shuffled:
            if (button.label or "").lower() in self.second_priority:
                return button
        for button in shuffled:
            if (button.label or "").lower() not in self.avoid:
                return button
        return None

    async def _handle(self, message):
        # Components_v2 crime prompt (container + text_display + buttons).
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        # Timeout edit ("Too scared to commit a crime huh?") carries no
        # prompt, so check it BEFORE the prompt gate.
        if any("Too scared" in t for t in texts):
            return
        if not any("What crime do you want to commit?" in t for t in texts):
            return

        clickable = [b for b in message.buttons if not b.disabled]
        if not clickable:
            return
        button = self._pick(clickable)
        if button is None:
            return
        await self.bot.click_button(button)
        self.bot.log(f"crime - clicked {button.label}", "green")

    async def log_messages(self, message):
        await self._handle(message)

    async def log_messages_edit(self, message):
        await self._handle(message)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Legacy embeds fallback (kept in case Dank Memer sends v1).
        if message.embeds:
            desc = message.embeds[0].description or ""
            if "What crime do you want to commit?" in desc:
                try:
                    children = list(enumerate(message.components[0].children))
                except (IndexError, AttributeError, TypeError):
                    return
                self.bot.random.shuffle(children)
                for count, button in children:
                    if (button.label or "").lower() in self.priority and not getattr(
                        button, "disabled", False
                    ):
                        await self.bot.click(message, 0, count)
                        return
                for count, button in children:
                    if (button.label or "").lower() in self.second_priority and not getattr(
                        button, "disabled", False
                    ):
                        await self.bot.click(message, 0, count)
                        return
                for count, button in children:
                    if (button.label or "").lower() not in self.avoid and not getattr(
                        button, "disabled", False
                    ):
                        await self.bot.click(message, 0, count)
                        return


async def setup(bot):
    await bot.add_cog(Crime(bot))
