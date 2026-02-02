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
        if message.channel.id != self.bot.channel.id:
            return
        
        if message.embeds:
            if "What crime do you want to commit?" in message.embeds[0].description:
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
    await bot.add_cog(Crime(bot))