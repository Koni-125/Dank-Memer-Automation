import asyncio
import json
import logging
import os
import random
import sys
import threading
from datetime import datetime
from pathlib import Path

import discord.errors
from discord import SlashCommand
from discord.ext import commands

import components_v2

from utils.custom_logger import CustomLogger
from utils.dashboard_server import DashboardState, run_dashboard_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


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
    # normal colors
    black = "\033[30m"
    red = "\033[31m"
    green = "\033[32m"
    yellow = "\033[33m"
    blue = "\033[34m"
    purple = "\033[35m"
    cyan = "\033[36m"
    white = "\033[37m"
    orange = "\033[93m"
    pink = "\033[95m"

    # light colors
    lightblack = "\033[90m"
    lightred = "\033[91m"
    lightgreen = "\033[92m"
    lightyellow = "\033[93m"
    lightblue = "\033[94m"
    lavender = "\033[95m"
    lightcyan = "\033[96m"
    lightwhite = "\033[97m"

    reset = "\033[0m"


DASHBOARD_STATE = DashboardState()
ROOT_DIR = Path(__file__).resolve().parent


def custom_print(message, time=True):
    DASHBOARD_STATE.add_log("info", message)
    if not time:
        print(f"{message}")
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


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
    class MyClient(commands.Bot):
        def log(self, text, color="default"):
            color_code = {
                "red": Colors.red,
                "green": Colors.green,
                "yellow": Colors.yellow,
                "default": Colors.reset,
            }.get(color, Colors.reset)

            who = self.user if self.user else f"Bot {self.channel_id}"
            custom_print(f"{color_code}[{who}]: {text}{Colors.reset}")

        def __init__(self, token, channel):
            super().__init__(
                command_prefix="-", self_bot=True, enable_debug_events=True
            )
            self.state = False
            self.settings_dict = None
            self.channel_id = int(channel)  # CHANNEL!!! also check token
            self.token = token
            self.message_dispatcher = MessageDispatcher()
            self.channel = None
            self.sent_command_count = 0
            self.last_sent_command = None
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
                "tidy": "tidy",
                "dep_all": "deposit",
                "stream": "stream",
                "work": "work shift",
                "daily": "daily",
                "crime": "crime",
                "bal": "balance",
                "adventure": "adventure"
            }
            self.last_ran = {}
            # discord.py-self's module sets global random to fixed seed. reset that, locally.
            self.random = random.Random()

            for command in self.commands_dict:
                self.last_ran[command] = 0

        async def send_cmd(self, content, **kwargs):
            if not self.state:
                return
            command = content.split()
            try:
                slash_mode = self.settings_dict["settings"].get("slashCommands", False)
            except (KeyError, TypeError, AttributeError):
                slash_mode = False

            # While onboarding is running, every command must be a slash
            # command so onboarding objectives that track slash usage count.
            onboarding = self.get_cog("Onboarding")
            if onboarding is not None and onboarding.enabled():
                slash_mode = True

            if slash_mode:
                await self.send_slash(command, **kwargs)
            else:
                await self.channel.send(f"pls {' '.join(command)}")
                self.log(f"Sent: pls {' '.join(command)}", "green")
                self.sent_command_count += 1
                self.last_sent_command = f"pls {' '.join(command)}"

        async def send_slash(self, command, **kwargs):
            # command is the split tokens (e.g. ["cointoss", "50000"]).
            if not self.state or not command:
                return
            try:
                commands = await self.channel.application_commands()
            except discord.errors.Forbidden:
                return
            except Exception as e:
                self.log(f"Error fetching commands: {e}", "red")
                await self.channel.send(f"pls {' '.join(command)}")
                return

            name = command[0]
            target = None
            for cmd in commands:
                if (
                    cmd.application.id != 270904126974590976
                    or not isinstance(cmd, SlashCommand)
                ):
                    continue
                cn = cmd.name.lower()
                if cn == name.lower():
                    target = cmd
                    break
                if cn.startswith(name.lower()):
                    target = cmd
                    break
            if target is None:
                for cmd in commands:
                    if (
                        cmd.application.id != 270904126974590976
                        or not isinstance(cmd, SlashCommand)
                    ):
                        continue
                    if name.lower() in cmd.name.lower():
                        target = cmd
                        break
            if target is None:
                self.log(f"Slash command not found: {name}", "red")
                return

            # Walk down subcommands (e.g. shop sell, title set, multipliers luck).
            node = target
            i = 1
            while i < len(command) and node.children:
                child = next(
                    (c for c in node.children if c.name.lower() == command[i].lower()),
                    None,
                )
                if child is None:
                    break
                node = child
                i += 1

            if node.is_group():
                self.log(f"Slash group cannot be invoked: {' '.join(command)}", "red")
                return

            # Remaining tokens become option values, filled positionally by
            # the command's declared option names (e.g. bet, item, title).
            for idx, tok in enumerate(command[i:]):
                if idx < len(node.options):
                    kwargs.setdefault(node.options[idx].name, tok)

            try:
                await node(channel=self.channel, **kwargs)
                self.log(f"Sent: /{' '.join(command)}", "green")
                self.sent_command_count += 1
                self.last_sent_command = f"/{' '.join(command)}"
            except (
                discord.errors.Forbidden,
                discord.errors.DiscordServerError,
                discord.errors.InvalidData,
                KeyError,
            ) as e:
                self.log(
                    f"Error: Command Unsuccessful\n{type(e).__name__}: {e}",
                    "red",
                )

        async def set_command_hold_stat(self, value):
            if value:
                self.hold_command = True
                self.state_event.set()
            else:
                self.hold_command = False
                self.state_event.clear()
                self.state_event.set()
                await asyncio.sleep(0)

        async def wait_until_command_released(self):
            while self.hold_command:
                await self.state_event.wait()
                await asyncio.sleep(0.05)

        async def is_valid_command(self, message, command) -> bool: #unused for now
            if message.channel.id != self.channel_id or message.author.id != 270904126974590976:
                return False
            
            if not self.settings_dict["settings"]["slashCommandMode"]:
                if message.reference is not None:
                    if message.reference.resolved is not None:
                        if message.reference.resolved.content != f'pls {command}' and message.reference.resolved.author.id != self.bot.user.id:
                            return False
            else:
                if self.settings_dict["settings"]["flowMode"]:
                    if message.reference is not None:
                        if message.reference.resolved is not None:
                            if not message.reference.resolved.ephemeral:
                                return False
                else:
                    pass
            
            return True

        async def click(self, message, component, children, delay=None):
            cooldowns = self.settings_dict["settings"]["cooldowns"]
            wait_time = delay if delay is not None else self.random.uniform(
                cooldowns["minButtonClickDelay"],
                cooldowns["maxButtonClickDelay"],
            )

            await self.set_command_hold_stat(True)
            try:
                await asyncio.sleep(wait_time)
                await message.components[component].children[children].click()
            except (discord.errors.HTTPException, discord.errors.InvalidData) as e:
                print("\n--- [DISCORD API ERROR] ---")
                
                # 1. Get the HTTP Status (e.g., 400, 401, 403, 429)
                status = getattr(e, 'status', 'Unknown Status')
                
                # 2. Get the Discord Internal Error Code (e.g., 50035)
                code = getattr(e, 'code', 'No Error Code')
                
                # 3. Get the raw text/message from the API
                # Most dpy-self errors have a .text or .message attribute
                error_msg = getattr(e, 'text', str(e))
                
                print(f"Status: {status}")
                print(f"Discord Code: {code}")
                print(f"Details: {error_msg}")
                
                # 4. Check for common self-bot failures
                if status == 429:
                    print("CRITICAL: You are being rate limited. Increase your asyncio.sleep() times.")
                elif status == 400:
                    print("FAILED: Invalid Interaction. Likely the custom_id expired or the message is too old.")
                elif status == 403:
                    print("FAILED: Forbidden. Check if the message is ephemeral or if you lack permissions.")
                    
                print("---------------------------\n")
            finally:
                if self.hold_command:
                    await self.set_command_hold_stat(False)
            # except (discord.errors.HTTPException, discord.errors.InvalidData) as e:
            #     pass
            
        async def select(self, message, component, children, option, delay=None):
            cooldowns = self.settings_dict["settings"]["cooldowns"]
            wait_time = delay if delay is not None else self.random.uniform(
                cooldowns["minButtonClickDelay"],
                cooldowns["maxButtonClickDelay"],
            )

            await asyncio.sleep(wait_time)
            try:
                select_menu = message.components[component].children[children]
                await select_menu.choose(select_menu.options[option])
            except (discord.errors.HTTPException, discord.errors.InvalidData):
                pass

        async def click_button(self, button, delay=None):
            # Click a components_v2 button (custom accessory) using the raw
            # interaction API. Used by dispatcher (custom message) handlers.
            # A nonce is registered with dpy so follow-up modal events (e.g.
            # pet rename) are dispatched to wait_for("modal").
            cooldowns = self.settings_dict["settings"]["cooldowns"]
            wait_time = delay if delay is not None else self.random.uniform(
                cooldowns["minButtonClickDelay"],
                cooldowns["maxButtonClickDelay"],
            )

            await self.set_command_hold_stat(True)
            try:
                await asyncio.sleep(wait_time)
                from discord.utils import _generate_nonce

                nonce = _generate_nonce()
                self._connection._interaction_cache[nonce] = (
                    3,  # InteractionType.component
                    None,
                    self.channel,
                )
                self._connection._interaction_cache.move_to_end(nonce)
                return await button.click(
                    self.ws.session_id,
                    self.local_headers,
                    str(self.channel.guild.id),
                    nonce=nonce,
                )
            except (discord.errors.HTTPException, discord.errors.InvalidData, AttributeError):
                return False
            finally:
                if self.hold_command:
                    await self.set_command_hold_stat(False)

        async def setup_hook(self):
            # self.update.start()
            self.settings_dict = get_config()
            self.logger = CustomLogger()
            # self.log = self.logger.log
            # self.log = log
            self.channel = await self.fetch_channel(self.channel_id)

            for filename in sorted(os.listdir(resource_path("./cogs"))):
                if not filename.endswith(".py"):
                    continue
                if filename.startswith("__"):
                    continue
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                except Exception as e:
                    self.log(f"Failed to load cog {filename}: {e}", "red")
            self.local_headers = await components_v2.headers.generate_headers()
            self.local_headers["Authorization"] = self.token
            self.log(f"Logged in as {self.user}", "green")
            self.state = True
            self.worth = {
                "coins" : 0,
                "inventory": 0,
                "net" : 0
            }
            DASHBOARD_STATE.register_bot(self)

        async def on_socket_raw_receive(self, msg):
            parsed_msg = json.loads(msg)
            if parsed_msg.get("t") not in ["MESSAGE_CREATE", "MESSAGE_UPDATE"]:
                return

            # Hardcoded raw-gateway dump for debugging. Always written so we
            # don't need to remember an env var.
            try:
                with open("/tmp/opencode/raw_dump.log", "a", encoding="utf-8") as _f:
                    _f.write(json.dumps(parsed_msg) + "\n")
            except OSError:
                pass

            message = components_v2.message.get_message_obj(parsed_msg["d"])

            if not components_v2.message.is_message_for_user(message, self.user.id):
                return

            if message.channel.id != self.channel_id:
                return

            if not self.state:
                return

            if parsed_msg["t"] == "MESSAGE_CREATE":
                await self.message_dispatcher.dispatch_on_message(message)
            else:
                await self.message_dispatcher.dispatch_on_edit(message)

    client = MyClient(token, channel_id)
    try:
        await client.start(token)
    except discord.errors.LoginFailure:
        client.log("Invalid token", "red")
        await client.close()
    except (discord.errors.NotFound, ValueError):
        client.log("Invalid channel", "red")
        await client.close()
    except Exception as e:
        print(e)
    finally:
        DASHBOARD_STATE.unregister_bot(client)


# Create and start the event loop in a separate thread
def start_event_loop(event_loop):
    asyncio.set_event_loop(event_loop)
    try:
        event_loop.run_forever()
    except BaseException:
        logging.exception("Fatal error in bot event loop thread")
    finally:
        logging.warning("Bot event loop thread exited")


loop = asyncio.new_event_loop()
t = threading.Thread(target=start_event_loop, args=(loop,))
t.start()

if __name__ == "__main__":
    # Print header and version information
    header = r"""
____              _       __  __                              ____      _           _
|  _ \  __ _ _ __ | | __  |  \/  | ___ _ __ ___   ___ _ __    / ___|_ __(_)_ __   __| | ___ _ __
| | | |/ _` | '_ \| |/ /  | |\/| |/ _ \ '_ ` _ \ / _ \ '__|  | |  _| '__| | '_ \ / _` |/ _ \ '__|
| |_| | (_| | | | |   <   | |  |  | __/ | | | | |  __/ |     | |_| | |  | | | | | (_| |  __/ |
|____/ \__,_|_| |_|_|\_\  |_|  |_|\___|_| |_| |_|\___|_|      \____|_|  |_|_| |_|\__,_|\___|_|
    """
    custom_print(header, False)
    custom_print(f"{Colors.lavender}v1.5.2", False)
    custom_print(f"{Colors.lightcyan}Dashboard: http://127.0.0.1:3000", False)

    def _run_dashboard():
        try:
            run_dashboard_server(
                DASHBOARD_STATE,
                ROOT_DIR / "settings.json",
                ROOT_DIR,
                host="127.0.0.1",
                port=3000,
            )
        except Exception:
            logging.exception("Dashboard server thread crashed")

    dashboard_thread = threading.Thread(target=_run_dashboard, daemon=True)
    dashboard_thread.start()

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

    def log_future_exception(future):
        try:
            future.result()
        except Exception as e:
            print(f"Bot crashed:", e)

    for item in tokens_and_channels:
        future = asyncio.run_coroutine_threadsafe(start_bot(item[0], item[1]), loop)
        future.add_done_callback(log_future_exception)
        futures.append(future)

    t.join()
