import contextlib
import asyncio
import json
import os, sys

from discord.ext import commands


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        # noinspection PyProtectedMember
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


with open(resource_path("resources/adventure.json"), encoding="utf-8") as file:
    adventure_dict = json.load(file)


class Adventure(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.adventure = self.bot.settings_dict["commands"]["adventure"]["adventure"]


    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
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
                        await self.bot.click(after, count, 0)
                        return
                return
            
        with contextlib.suppress(KeyError):
            embed = after.embeds[0].to_dict()
            if "You can start another adventure at" in embed["description"]:
                await self.bot.set_command_hold_stat(False)
                return

            for i in range(3):
                with contextlib.suppress(AttributeError):
                    button = after.components[i].children[1]
                    # if not button.disabled and button.emoji.id == 1067941108568567818:
                    if not button.disabled and button.emoji.id == 1379166099895091251:
                        await self.bot.click(after, i, 1)
                        return

            if "Catch one of em!" in embed["description"]:
                await self.bot.click(after, 0 , 2)
                await self.bot.click(after, 1 , 1)
                return

            question = embed["description"].split("\n")[0]
            for q, answer in adventure_dict["adventure"][
                self.adventure
            ].items():
                if q.lower() in question.lower():
                    for count, button in enumerate(after.components[0].children):
                        if button.label.lower() == answer.lower():
                            await self.bot.click(after, 0, count)

    @commands.Cog.listener()
    async def on_message(self, message):
        with contextlib.suppress(KeyError):
            embed = message.embeds[0].to_dict()
            if "Choose an Adventure" in embed["author"]["name"]:
                await self.bot.set_command_hold_stat(True)
                for count, i in enumerate(message.components[0].children[0].options):
                    if i.value == self.adventure:
                        await self.bot.select(message, 0, 0, count)
                        if not message.components[1].children[0].disabled:
                            await asyncio.sleep(0.5)
                            await self.bot.click(message, 1, 0)
                        else:
                            await self.bot.set_command_hold_stat(False)




async def setup(bot):
    await bot.add_cog(Adventure(bot))
