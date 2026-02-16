from discord.ext import commands
import re
import asyncio

class Work(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_messages)



    async def work_apply(self):
        await self.bot.set_command_hold_stat(True)
        await self.bot.send_cmd("work list")

        def validate(msg):
            if msg.author.id != 270904126974590976:
                return False
            
            if msg.reference is not None and msg.reference.resolved is not None:
                if msg.reference.resolved.content != f'pls work list' and msg.reference.resolved.author != self.bot.user.id:
                    return False
            try:
                return msg.embeds[0].to_dict()["title"] == "Available Jobs"
            except (KeyError, IndexError):
                return False
            
        message = await self.bot.wait_for("message", check=validate)
        embed = message.embeds[0].to_dict()
        pages = int(re.search(r"Page \d+ of (\d+)", embed["footer"]["text"]).group(1))
        locked_jobs = []
        unlocked_jobs = []
        for page in range(pages):
            embed = message.embeds[0].to_dict()
            pattern = r'(<:C[XY]:\d+>)\s+(?:\[\*\*|\*\*)(.*?)(?:\*\*\]|\*\*)'

            matches = re.findall(pattern, embed["description"])

            unlocked_jobs.extend(
                name for emoji, name in matches if "CY" in emoji
            )

            locked_jobs.extend(
                name for emoji, name in matches if "CX" in emoji
            )
            if len(locked_jobs) > 0:
                await self.bot.send_cmd(f"work apply {unlocked_jobs[len(unlocked_jobs) - 1]}")
                await self.bot.set_command_hold_stat(False)
                return
            else:
                await self.bot.click(message, 0, 2)
                await asyncio.sleep(0.5)
    
    async def log_messages(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                if component.component_name == "text_display":
                    if "You don't currently have a job to work at" in component.content:
                        await self.work_apply()





async def setup(bot):
    await bot.add_cog(Work(bot))
