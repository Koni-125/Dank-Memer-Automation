import asyncio
import json
import os
import random
import sys
import threading
from datetime import datetime

import discord.errors
import requests
from discord.ext import commands

import components_v2


def get_config():
    try:
        with open("settings.json", "r") as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        print("ERROR - whoops, no settings file found!")


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class Colors:
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    orange = "\033[93m"
    reset = "\033[0m"


def custom_print(message, time=True):
    if not time:
        print(f"\r{message}", end="\n> ")
    else:
        print(f"\r[{datetime.now().strftime('%H:%M:%S')}] {message}", end="\n> ")


def handle_user_input():
    while True:
        user_input = input().encode("utf-8", errors="ignore").decode("utf-8")

        if user_input == "help":
            custom_print(f"{Colors.orange}quit:{Colors.reset} Stop the code")
        elif user_input == "quit":
            custom_print(f"{Colors.yellow}stopping code...{Colors.reset}")
            os._exit(0)
        else:
            custom_print(
                f'{Colors.red}Unknown command. Type "help" for a list of commands{Colors.reset}'
            )


class MessageDispatcher:
    """
    This is used like a middle man between on_socket_raw_receive and
    reciever functions
    """

    def __init__(self):
        self._message_handlers = []
        self._edit_handlers = []

    def register(self, func, edit=False):
        if not edit:
            self._message_handlers.append(func)
        else:
            self._edit_handlers.append(func)

    async def dispatch_on_message(self, message):
        for handler in self._message_handlers:
            await handler(message)

    async def dispatch_on_edit(self, message):
        for handler in self._edit_handlers:
            await handler(message)


async def start_bot(token, channel_id):
    @staticmethod
    def log(text, color="default"):
        color_code = {
            "red": Colors.red,
            "green": Colors.green,
            "yellow": Colors.yellow,
            "default": Colors.reset,
        }.get(color, Colors.reset)

        # Fix incorrect logs
        custom_print(f"{color_code}Bot {channel_id}: {text}{Colors.reset}")

    class MyClient(commands.Bot):
        def __init__(self, token, channel):
            super().__init__(
                command_prefix="-", self_bot=True, enable_debug_events=True
            )
            self.state = False
            self.settings_dict = None
            self.channel_id = channel  # CHANNEL!!! also check token
            self.token = token
            self.log = log
            self.message_dispatcher = MessageDispatcher()
            self.channel = None
            # --
            self.hold_command = False
            self.state_event = asyncio.Event()
            # --

            self.commands_dict = {
                "trivia": "trivia",
                "dig": "dig",
                "fish": "fish",
                "hunt": "hunt",
                "pm": "postmemes",
                "beg": "beg",
                "pet": "pets",
                "scratch": "scratch",
                "hl": "highlow",
                "search": "search",
                "dep_all": "deposit",
                "stream": "stream",
                "work": "work",
                "daily": "daily",
                "crime": "crime",
                "adventure": "adventure",
            }
            self.last_ran = {}
            # discord.py-self's module sets global random to fixed seed. reset that, locally.
            self.random = random.Random()

            for command in self.commands_dict:
                self.last_ran[command] = 0

        async def send_cmd(self, content):
            if self.state:
                # send text based command
                await self.channel.send(f"pls {content}")

        async def set_command_hold_stat(self, value):
            if value:
                self.hold_command = True
                self.state_event.set()
            else:
                while not self.hold_command:
                    await self.state_event.wait()
                self.hold_command = False
                self.state_event.clear()

        async def setup_hook(self):
            # self.update.start()
            self.settings_dict = get_config()
            self.channel = await self.fetch_channel(self.channel_id)

            for filename in os.listdir(resource_path("./cogs")):
                if filename.endswith(".py"):
                    # print(f'{filename[:-3]}')
                    await self.load_extension(f"cogs.{filename[:-3]}")
            self.local_headers = await components_v2.headers.generate_headers()
            self.local_headers["Authorization"] = self.token
            self.log(f"Logged in as {self.user}", "green")
            self.state = True

        async def on_socket_raw_receive(self, msg):
            parsed_msg = json.loads(msg)
            if parsed_msg.get("t") not in ["MESSAGE_CREATE", "MESSAGE_UPDATE"]:
                return

            message = components_v2.message.get_message_obj(parsed_msg["d"])

            if parsed_msg["t"] == "MESSAGE_CREATE":
                await self.message_dispatcher.dispatch_on_message(message)
            else:
                await self.message_dispatcher.dispatch_on_edit(message)

    client = MyClient(token, channel_id)
    try:
        await client.start(token)
    except discord.errors.LoginFailure:
        log("Invalid token", "red")
        await client.close()
    except (discord.errors.NotFound, ValueError):
        log("Invalid channel", "red")
        await client.close()
    except Exception as e:
        print(e)


# Create and start the event loop in a separate thread
def start_event_loop(event_loop):
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()


loop = asyncio.new_event_loop()
t = threading.Thread(target=start_event_loop, args=(loop,))
t.start()

if __name__ == "__main__":
    # Start the user_input_thread
    user_input_thread = threading.Thread(target=handle_user_input)
    user_input_thread.start()

    # Fetch version information
    version_url = "https://raw.githubusercontent.com/BridgeSenseDev/Dank-Memer-Grinder/main/resources/version.txt"
    version = requests.get(version_url).text

    # Print header and version information
    header = """
____              _       __  __                              ____      _           _
|  _ \  __ _ _ __ | | __  |  \/  | ___ _ __ ___   ___ _ __    / ___|_ __(_)_ __   __| | ___ _ __
| | | |/ _` | '_ \| |/ /  | |\/| |/ _ \ '_ ` _ \ / _ \ '__|  | |  _| '__| | '_ \ / _` |/ _ \ '__|
| |_| | (_| | | | |   <   | |  | |  __/ | | | | |  __/ |     | |_| | |  | | | | | (_| |  __/ |
|____/ \__,_|_| |_|_|\_\  |_|  |_|\___|_| |_| |_|\___|_|      \____|_|  |_|_| |_|\__,_|\___|_|
    """
    custom_print(header, False)
    custom_print("\033[33mv1.5.2", False)
    custom_print('\033[33mType "help" for a list of commands', False)

    # Check for updates
    """if int(version.replace(".", "")) > 152:
        update_url = f"https://github.com/BridgeSenseDev/Dank-Memer-Grinder/releases/tag/vf{version}"
        custom_print(
            f"A new version v{version} is available, download it here:\n{update_url}"
        )"""

    # Read tokens.txt and start bots
    with open("tokens.txt", "r") as f:
        tokens_and_channels = [line.strip().split() for line in f if line.strip()]

    futures = []

    for item in tokens_and_channels:
        future = asyncio.run_coroutine_threadsafe(start_bot(item[0], item[1]), loop)
        futures.append((item, future))

    # surface exceptions from the event loop thread
    for item, future in futures:
        try:
            future.result()
        except Exception as e:
            print(f"Bot {item} crashed:", e)

    t.join()
