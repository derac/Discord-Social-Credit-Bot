
import os, json, time
from datetime import datetime, timedelta, timezone

import aiohttp, discord
from discord.ext import commands
from dotenv import load_dotenv

# will use this model because chinese and it's the best one probably
# https://openrouter.ai/models?q=free&supported_parameters=structured_outputs
# qwen/qwen3-235b-a22b:free

load_dotenv()
description = """A bot that takes the previous day's messages and puts them into an llm model's context.
It creates a social credit score for each user and displays that in a table.
Then, it assigns roles based on the social credit score."""

SYSTEM_PROMPT = "You are a discord bot which seeks to assign a social credit score to all users in \
a discord server based on the history of their messages from the past day. Good behavior should \
score well, while bad behavior should score poorly."

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", description=description, intents=intents)
SCAN_PERIOD = timedelta(hours=24)


@bot.event
async def on_ready():
    global SESSION
    SESSION = aiohttp.ClientSession()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})\n")


@bot.command()
async def allchats(ctx):
    GUILD_ID = ctx.guild.id
    guild = bot.get_guild(GUILD_ID)
    all_channel_message_log = ""

    for channel in guild.channels:
        if channel.type == discord.ChannelType.text:
            all_channel_message_log += f"\n# Channel - {channel.name.capitalize()}\n"
            async for message in channel.history():
                message_time_difference = (
                    datetime.now(timezone.utc) - message.created_at
                )
                if message_time_difference < SCAN_PERIOD:
                    all_channel_message_log += f"{message.author}: {message.content}\n"
                else:
                    break
    print(all_channel_message_log)
    json_data = {
        "model": "qwen/qwen3-235b-a22b:free",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": all_channel_message_log},
        ],
        # "temperature": 0.7,
        # "top_p": 1,
        # "frequency_penalty": 0,
        # "presence_penalty": 0,
        "provider": {
            "allow_fallbacks": True,
            "sort": "latency",
            "data_collection": "deny",
        },
        "max_tokens": 100,
    }
    headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_KEY')}",
            "Content-Type": "application/json"
        }
    
    while True:
        async with SESSION.post(url="https://openrouter.ai/api/v1/chat/completions", headers=headers, data=json.dumps(json_data)) as response:
            if response.status == 200:
                data = await response.json()
                print(data)
                break
            elif response.status == 429:
                time.sleep(5)
                continue
            else:
                print(f"Error fetching data: {response.status}")
                break



bot.run(os.getenv("DISCORD_TOKEN"))
