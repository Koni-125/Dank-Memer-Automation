import random

from discord.ext import commands


class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        search_config = self.bot.settings_dict["commands"]["search"]

        self.priority = search_config["priority"]
        self.second_priority = search_config["second_priority"]
        self.avoid = search_config["avoid"]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        if message.embeds:
            if "Where do you want to search?" in message.embeds[0].description:
                children = list(enumerate(message.components[0].children))
                random.shuffle(children)
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
