import json
import os
import random
import re
import sys

from discord.ext import commands


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        # noinspection PyProtectedMember
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


with open(resource_path("resources/trivia.json")) as file:
    trivia_dict = json.load(file)


class Trivia(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.bot.message_dispatcher.register(self.log_messages)
        self.chance = self.bot.settings_dict["commands"]["trivia"][
            "trivia_correct_chance"
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.channel.id:
            return

        if message.embeds:
            desc = message.embeds[0].description
            if "seconds to answer" in desc:
                question = re.search(r"\*\*(.*?)\*\*", desc)[1]
                category = message.embeds[0].fields[1].value
                answer = trivia_dict[category].get(question, None)
                if not answer:
                    child = self.bot.random.randint(0, 3)
                    await message.components[0].children[child].click()
                    self.bot.log("Triva fail", "red")
                    return

                for count, i in enumerate(message.components[0].children):
                    if i.label == answer:
                        if random.random() <= self.chance:
                            await i.click()
                            self.bot.log("Triva success", "green")
                        else:
                            choices = [i for i in [0, 1, 2, 3] if i != count]
                            await (
                                message.components[0]
                                .children[self.bot.random.choice(choices)]
                                .click()
                            )
                            self.bot.log("Triva fail - intentional", "red")


async def setup(bot):
    await bot.add_cog(Trivia(bot))
