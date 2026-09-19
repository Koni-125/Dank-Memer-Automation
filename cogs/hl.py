import re
import time

import components_v2

from discord.ext import commands


class Hl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)

    async def log_messages(self, message):
        # Components_v2 high-low prompt (container + text_display + buttons).
        if message.channel_id != self.bot.channel.id:
            return

        texts = components_v2.message.text_display_contents(message)
        joined = "\n".join(texts)
        if "high-low game" not in joined or "Is the secret number" not in joined:
            return
        if "expired" in joined:
            return

        # Hint number must sit next to "secret number" -- a bet amount or
        # other bold figure earlier in the message must not be read as
        # the hint.
        secret_idx = joined.find("secret number")
        hint_region = joined[secret_idx:] if secret_idx != -1 else joined
        match = re.search(r"\*\*(\d+)\*\*", hint_region)
        if not match:
            return
        num = int(match.group(1))

        # Buttons are [Lower, JACKPOT, Higher]. A high hint makes
        # "lower" more likely and vice versa.
        want = "Lower" if num >= 50 else "Higher"
        for button in message.buttons:
            if button.label == want and not button.disabled:
                if await self.bot.click_button(button):
                    self.bot.log(f"hl clicked {want} (hint {num})", "green")
                    self.bot.last_ran["hl"] = time.time()
                else:
                    self.bot.log(f"hl click failed ({want}, hint {num})", "red")
                return

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
            embed = message.embeds[0]
            author_name = embed.author.name if embed.author else ""
            if author_name is None or "high-low" not in author_name:
                return
            self.bot.log("hl detected", "green")

            desc = embed.description or ""
            match = re.search(r"\*\*(.*?)\*\*", desc)
            if not match:
                return
            num = int(match.group(1))
            # Buttons are [Lower, JACKPOT, Higher]. A high hint makes
            # "lower" more likely and vice versa.
            try:
                children = message.components[0].children
            except (IndexError, AttributeError, TypeError):
                return
            if not children or len(children) < 3:
                return
            if not getattr(children[0], "disabled", False) and num >= 50:
                clicked = await self.bot.click(message, 0, 0)
            elif not getattr(children[2], "disabled", False) and num < 50:
                clicked = await self.bot.click(message, 0, 2)
            else:
                return
            if clicked:
                self.bot.last_ran["hl"] = time.time()
            else:
                self.bot.log("hl click failed (legacy)", "red")


async def setup(bot):
    await bot.add_cog(Hl(bot))
