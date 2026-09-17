import components_v2

from discord.ext import commands


class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        search_config = self.bot.settings_dict["commands"]["search"]

        self.priority = search_config["priority"]
        self.second_priority = search_config["second_priority"]
        self.avoid = search_config["avoid"]
        self.bot.message_dispatcher.register(self.log_messages)

    def _pick(self, buttons):
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

    async def log_messages(self, message):
        # Components_v2 search prompt (container + text_display + buttons).
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        if not any("Where do you want to search?" in t for t in texts):
            return
        # Timeout edit ("Guess you didn't want to search anywhere?").
        if any("didn't want to search" in t for t in texts):
            return

        clickable = [b for b in message.buttons if not b.disabled]
        if not clickable:
            return
        button = self._pick(clickable)
        if button is None:
            return
        await self.bot.click_button(button)
        self.bot.log(f"search - clicked {button.label}", "green")

    @commands.Cog.listener()
    async def on_message(self, message):
        # Legacy embeds fallback (kept in case Dank Memer sends v1).
        try:
            if message.channel.id != self.bot.channel.id:
                return
        except AttributeError:
            return
        if getattr(getattr(message, "author", None), "id", None) != 270904126974590976:
            return
        if message.embeds:
            desc = message.embeds[0].description or ""
            if "Where do you want to search?" in desc:
                children = list(enumerate(message.components[0].children))
                self.bot.random.shuffle(children)
                for count, button in children:
                    if button.label.lower() in self.priority:
                        await self.bot.click(message, 0, count)
                        return
                for count, button in children:
                    if button.label.lower() in self.second_priority:
                        await self.bot.click(message, 0, count)
                        return
                for count, button in children:
                    if button.label.lower() not in self.avoid:
                        await self.bot.click(message, 0, count)
                        return


async def setup(bot):
    await bot.add_cog(Search(bot))
