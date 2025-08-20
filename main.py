import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from modules.social_credit import SocialCredit

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
description = """A bot that takes the previous day's messages and puts them into an llm model's context.
It creates a social credit score for each user and displays that in a table.
Then, it assigns roles based on the social credit score. The numbers should be between -100 and 100."""
bot = commands.Bot(command_prefix="!", description=description, intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})\n")
    await bot.add_cog(SocialCredit(bot))


bot.run(os.getenv("DISCORD_TOKEN"))
