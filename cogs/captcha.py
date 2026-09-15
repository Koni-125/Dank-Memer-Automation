from discord.ext import commands

DANK_MEMER_ID = 270904126974590976


class Captcha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.channel.id != self.bot.channel.id:
                return
        except AttributeError:
            return
        if getattr(getattr(message, "author", None), "id", None) != DANK_MEMER_ID:
            return
        if not message.embeds:
            return
        embed = message.embeds[0]
        title = embed.title or ""
        desc = embed.description or ""
        # Real Dank Memer captcha embed: title "Captcha", description links
        # dankmemer.lol/captcha. (NOT "Verification Required" -- that string
        # never appears; verified against logs/raw-2026-09-15.log line 2088.)
        if title.strip().lower() != "captcha" and "dankmemer.lol/captcha" not in desc:
            return
        # Full stop: both command loops gate on bot.state, and misc.py
        # already halts on the same message. Latch so nothing resumes
        # until a human clears it.
        await self.bot.set_command_hold_stat(True)
        self.bot.state = False
        self.bot.log(
            "CAPTCHA DETECTED - bot stopped. Solve it manually, then restart.",
            "red",
        )


async def setup(bot):
    await bot.add_cog(Captcha(bot))
