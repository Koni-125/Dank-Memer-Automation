import random

from discord.ext import commands


class Search(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        search_config = self.bot.settings_dict["commands"]["crime"]

        self.priority = search_config["priority"]
        self.second_priority = search_config["second_priority"]
        self.avoid = search_config["avoid"]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        if message.embeds:
            if "Where do you want to search?" in message.embeds[0].description:
                children = message.components[0].children
                random.shuffle(children)
                for count, button in enumerate(children):
                    if button.label.lower() in self.priority:
                        await button.click()
                        return
                for count, button in enumerate(children):
                    if button.label.lower() in self.second_priority:
                        await button.click()
                        return
                for count, button in enumerate(children):
                    if button.label.lower() not in self.avoid:
                        await button.click()
                        return


async def setup(bot):
    await bot.add_cog(Search(bot))
