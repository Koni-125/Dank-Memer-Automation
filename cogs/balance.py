from discord.ext import commands
import re

class Balance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.message_dispatcher.register(self.log_message)
        self.bot.message_dispatcher.register(self.log_messages_edit, edit=True)
       

    
    async def log_message(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                if component.component_name == "section":
                    for cmp in component.components:
                        if cmp.component_name == "text_display":
                            if not f"### {self.bot.user.global_name}'s Balances".lower() in cmp.content.lower():
                                return
                    try:
                        await component.accessory.click(
                            self.bot.ws.session_id,
                            self.bot.local_headers,
                            str(self.bot.channel.guild.id)
                        )
                    except Exception as e:
                        pass



    async def log_messages_edit(self, message):
        if message.channel_id != self.bot.channel.id:
            return

        if message.components:
            for component in message.components:
                if component.component_name == "section":
                    for cmp in component.components:
                        if cmp.component_name == "text_display":
                            if not f"### {self.bot.user.global_name}'s Net Worth".lower() in cmp.content.lower():
                                return   
                if component.component_name == "text_display":
                    text = component.content
                    coins = re.search(r'Coin:\d+>\s*([\d,]+)', text).group(1).replace(',', '')
                    inventory = re.search(r'Backpack:\d+>\s*([\d,]+)', text).group(1).replace(',', '')
                    total = re.search(r'BankrobIcon:\d+>\s*([\d,]+)', text).group(1).replace(',', '') 
                    self.bot.worth["coins"] = coins
                    self.bot.worth["inventory"] = inventory
                    self.bot.worth["worth"] = total
                    print(self.bot.worth)

async def setup(bot):
    await bot.add_cog(Balance(bot))
