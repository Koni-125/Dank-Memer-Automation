from discord.ext import commands


class Captcha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.embeds:
            title = message.embeds[0].title
            if "Verification Required" in title:
                self.bot.captcha = True


async def setup(bot):
    await bot.add_cog(Captcha(bot))
