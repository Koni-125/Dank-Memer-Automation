import asyncio
import re

import components_v2

from discord.ext import commands

DANK_MEMER_ID = 270904126974590976


class Work(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)

    async def work_apply(self):
        await self.bot.set_command_hold_stat(True)

        def validate(msg):
            if msg.author.id != DANK_MEMER_ID:
                return False
            if msg.reference is not None and msg.reference.resolved is not None:
                if (
                    msg.reference.resolved.content != "pls work list"
                    and msg.reference.resolved.author.id != self.bot.user.id
                ):
                    return False
            try:
                return msg.embeds[0].to_dict()["title"] == "Available Jobs"
            except (KeyError, IndexError, AttributeError):
                return False

        def validate_edit(_before, after):
            try:
                return after.embeds[0].to_dict()["title"] == "Available Jobs"
            except (KeyError, IndexError, AttributeError):
                return False

        try:
            await self.bot.send_cmd("work list")
            message = await self.bot.wait_for("message", check=validate, timeout=20)
        except asyncio.TimeoutError:
            self.bot.log("work apply timed out waiting for job list", "red")
            await self.bot.set_command_hold_stat(False)
            return
        if message is None:
            await self.bot.set_command_hold_stat(False)
            return

        embed = message.embeds[0].to_dict()
        pages = int(re.search(r"Page \d+ of (\d+)", embed["footer"]["text"]).group(1))
        unlocked_jobs = []

        for page in range(pages):
            embed = message.embeds[0].to_dict()
            pattern = r"(<:C[XY]:\d+>)\s+(?:\[\*\*|\*\*)(.*?)(?:\*\*\]|\*\*)"
            matches = re.findall(pattern, embed["description"])
            unlocked_jobs.extend(name for emoji, name in matches if "CY" in emoji)
            locked_jobs = [name for emoji, name in matches if "CX" in emoji]

            if unlocked_jobs and locked_jobs:
                await self.bot.send_cmd(f"work apply {unlocked_jobs[-1]}")
                await self.bot.set_command_hold_stat(False)
                return

            if page >= pages - 1:
                break

            try:
                await self.bot.click(message, 0, 2)
            except Exception as e:
                self.bot.log(f"work apply next-page click failed: {e}", "red")
                break
            try:
                result = await self.bot.wait_for(
                    "message_edit", check=validate_edit, timeout=20
                )
            except asyncio.TimeoutError:
                self.bot.log("work apply timed out waiting for next page", "red")
                break
            if result is None:
                break
            message = result[1]

        await self.bot.set_command_hold_stat(False)

    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if any(
            "You don't currently have a job to work at" in text
            for text in components_v2.message.text_display_contents(message)
        ):
            await self.work_apply()


async def setup(bot):
    await bot.add_cog(Work(bot))
