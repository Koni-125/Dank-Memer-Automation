from discord.ext import commands
import discord
import asyncio
import re

class AutoBuy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.buyRifle = False
        self.buyShovel = False
        self.bot.message_dispatcher.register(self.log_messages)

    

    async def shop_buy(self, item, count = 1):
        await self.bot.send_cmd("shop view")
        def validate(msg, after = None):
            if msg.author.id != 270904126974590976:
                return False
            
            if msg.reference is not None and msg.reference.resolved is not None:
                if msg.reference.resolved.content != f'pls shop view' and msg.reference.resolved.author != self.bot.user.id:
                    return False
            try:
                return msg.embeds[0].to_dict()["title"] == "Dank Memer Shop"
            except (KeyError, IndexError):
                return False
        message = await self.bot.wait_for("message", check=validate)
        await self.bot.select(message, 0, 0, 0)
        await asyncio.sleep(0.5)

        embed = message.embeds[0].to_dict()
        pages = int(re.search(r"Page \d+ of (\d+)", embed["footer"]["text"]).group(1))
        for i in range(pages):
            for row in range(1, 3):
                for col, button in enumerate(message.components[row].children):
                    if item in button.label.lower():
                        if message.components[row].children[col].disabled:
                            await self.bot.set_command_hold_stat(False)
                            return False
                        button = message.components[row].children[col]
                        asyncio.create_task(button.click())
                        modal = await self.bot.wait_for("modal")
                        modal.components[0].children[0].answer(str(count))
                        try:
                            await modal.submit()
                        except (
                            discord.errors.HTTPException,
                            discord.errors.InvalidData,
                        ):
                            pass
                        await self.bot.set_command_hold_stat(False)
                        return

            await self.bot.click(message, 3, 2)
            await asyncio.sleep(0.3)
        if self.bot.hold_command:
            await self.bot.set_command_hold_stat(False)
        return
    
    async def log_messages(self, message):  
        if message.channel_id != self.bot.channel.id:
            return
        
        if message.components:
            for component in message.components:
                if component.component_name == "text_display":
                    if "You don't have a shovel," in component.content:
                        await self.bot.set_command_hold_stat(True)
                        await self.shop_buy('shovel', 1)
                    elif 'You don\'t have a rifle' in component.content:
                        await self.bot.set_command_hold_stat(True)
                        await self.shop_buy('rifle', 1)
                    elif component.content == '### Pending Confirmation':
                        for btn in message.buttons:
                            if btn.label == 'Confirm':
                                stat = await btn.click(
                                        self.bot.ws.session_id,
                                        self.bot.local_headers,
                                        str(self.bot.channel.guild.id),

                                    )

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.channel.id != self.bot.channel.id:
                return


            if message.embeds:
                desc = message.embeds[0].description or ""
                
                if "You don't have a hunting rifle" in desc:
                    await self.bot.set_command_hold_stat(True)
                    await self.shop_buy('rifle', 1)
                elif "You don't have a shovel" in desc:
                    await self.bot.set_command_hold_stat(True)
                    await self.shop_buy('shovel', 1)
        except Exception as e:
            print(f"Error in on_message: {e}")
async def setup(bot):
    await bot.add_cog(AutoBuy(bot))
