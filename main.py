import os, logging, logging.handlers

import discord
from discord.ext import commands
from dotenv import load_dotenv

from modules.social_credit import SocialCredit

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.INFO)

handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)

load_dotenv()
intents = discord.Intents.default()
# needed to read chat history
intents.message_content = True
# needed to check roles
intents.guilds = True
# needed to get user objects to set roles and such
intents.members = True
description = """A bot that takes the previous day's messages and puts them into an llm model's context.
It creates a social credit score for each user and displays that in a table.
Then, it assigns roles based on the social credit score. The numbers should be between -100 and 100."""
bot = commands.Bot(command_prefix="!", description=description, intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})\n")
    await bot.add_cog(SocialCredit(bot, logger))


bot.run(os.getenv("DISCORD_TOKEN"), log_handler=None)
