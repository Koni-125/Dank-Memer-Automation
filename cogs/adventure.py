import contextlib
import asyncio

from discord.ext import commands


class Adventure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.adventure = self.bot.settings_dict["commands"]["adventure"]["adventure"]


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.channel.id != self.bot.channel_id:
            return

        if after.reference is not None:
            if after.reference.resolved is not None:
                if after.reference.resolved.content != 'pls adventure':
                    return
                
        with contextlib.suppress(KeyError):
            embed = after.embeds[0].to_dict()
            if embed["author"]["name"] == "Adventure Summary":
                await self.bot.set_command_hold_stat(False)

        with contextlib.suppress(KeyError):
            embed = after.embeds[0].to_dict()
            if "choose items you want to" in embed["title"]:
                for count, component in enumerate(after.components):
                    if component.children[0].label == "Start":
                        await after.components[count].children[0].click()
                        # await self.bot.click(after, count, 0)
                        return
                return
            
        with contextlib.suppress(KeyError):
            embed = after.embeds[0].to_dict()
            if "You can start another adventure at" in embed["description"]:
                await self.bot.set_command_hold_stat(False)
                return

            for i in range(2):
                with contextlib.suppress(AttributeError):
                    button = after.components[i].children[1]
                    if not button.disabled and button.emoji.id == 1067941108568567818:
                        await button.click()
                        # await self.bot.click(after, i, 1)
                        return

            if "Catch one of em!" in embed["description"]:
                await after.components[0].children[2].click()
                await after.components[1].children[1].click()
                return

            question = embed["description"].split("\n")[0]
            for q, answer in self.bot.adventure_config["adventure"][
                self.adventure
            ].items():
                if q.lower() in question.lower():
                    for count, button in enumerate(after.components[0].children):
                        if button.label.lower() == answer.lower():
                            await after.components[0].children[count].click()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel_id:
            return

        with contextlib.suppress(KeyError):
            embed = message.embeds[0].to_dict()
            if embed["author"]["name"] == "Choose an Adventure":
                await self.bot.set_command_hold_stat(True)
                for count, i in enumerate(message.components[0].children[0].options):
                    if i.value == self.adventure:
                        await self.bot.select(message, 0, 0, count)
                        if not message.components[1].children[0].disabled:
                            await asyncio.sleep(0.5)
                            await message.components[1].children[0].click()
                            # await self.bot.click(message, 1, 0)
                        else:
                            await self.bot.set_command_hold_stat(False)




async def setup(bot):
    await bot.add_cog(Adventure(bot))
