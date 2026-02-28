import random

from discord.ext import commands


class Crime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        crime_config = self.bot.settings_dict["commands"]["crime"]

        self.priority = crime_config["priority"]
        self.second_priority = crime_config["second_priority"]
        self.avoid = crime_config["avoid"]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.embeds:
            if "What crime do you want to commit?" in message.embeds[0].description:
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
    await bot.add_cog(Crime(bot))
