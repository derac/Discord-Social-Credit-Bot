import os, json, time
from datetime import datetime, timedelta, timezone

import aiohttp, discord
from discord.ext import commands
from dotenv import load_dotenv

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


class SocialCredit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.SESSION = aiohttp.ClientSession()
        self.SCAN_PERIOD = timedelta(hours=24)
        self.SYSTEM_PROMPT = "You are a discord bot which seeks to assign a social credit score to all users in \
        a discord server based on the history of their messages from the past day. Good behavior should \
        score well, while bad behavior should score poorly. Provide output as json. When writing reasoning \
        for the score you've given someone, make it concise and matter of fact. Speak like an impersonal \
        robot social credit system that looms over the chat and judges from on high."

    @commands.command()
    async def judge(self, ctx):
        AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
        if ctx.author.id != AUTHORIZED_USER_ID:
            await ctx.send("You are not authorized to use this command.")
            return
        GUILD_ID = ctx.guild.id
        guild = self.bot.get_guild(GUILD_ID)
        all_channel_message_log = ""
        all_users_with_messages = set()

        for channel in guild.channels:
            if channel.type == discord.ChannelType.text:
                all_channel_message_log += f"\n# Channel - {channel.name.capitalize()}\n"
                async for message in channel.history():
                    message_time_difference = (
                        datetime.now(timezone.utc) - message.created_at
                    )
                    if message_time_difference < self.SCAN_PERIOD:
                        all_channel_message_log += f"{message.author.name}: {message.content}\n"
                        all_users_with_messages.add(message.author.name)
                    else:
                        break
        all_users_with_messages = list(all_users_with_messages)
        print(all_channel_message_log)
        print(f"Fetched a message log of length {len(all_channel_message_log)}")
        #print(all_users_with_messages)
        print(f"{len(all_users_with_messages)} users: {all_users_with_messages}")
        schema_properties = dict()
        for user in all_users_with_messages:
            schema_properties[str(user)] = {
                "type": "object",
                "required": ["social_credit_score", "reasoning"],
                "properties": {
                    "social_credit_score": {"type":"number", "description": "A social credit score for this user. A number between -100 and 100", "minimum": -100, "maximum": 100},
                    "reasoning": {"type":"string","description":"Reasoning for giving this user this score."}
                },
                "additionalProperties": False,
            }
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "Social Credit scores for all users",
                "strict": True,
                "schema": {
                    "type": "object",
                    "required": [str(user) for user in all_users_with_messages],
                    "properties": schema_properties,
                    "additionalProperties": False,
                },
            },
        }
        json_data = {
            "model": "qwen/qwen3-235b-a22b:free",
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": all_channel_message_log},
            ],
            "provider": {
                "allow_fallbacks": True,
                "sort": "latency",
                "data_collection": "deny",
                "require_parameters": True,
            },
            "response_format": response_format,
            # "temperature": 0.7,
            # "top_p": 1,
            # "frequency_penalty": 0,
            # "presence_penalty": 0,
            # "max_tokens": 100,
        }
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_KEY')}",
            "Content-Type": "application/json",
        }

        while True:
            async with self.SESSION.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(json_data),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    social_credit_scores = json.loads(data["choices"][0]["message"]["content"])
                    print(social_credit_scores)
                    output = ""
                    for user, data in social_credit_scores.items():
                        social_credit_score = data["social_credit_score"]
                        reasoning = data["reasoning"]
                        output += f"{user} ({social_credit_score})\n{reasoning}\n\n"
                    await ctx.send(output)
                    break
                elif response.status == 429:
                    time.sleep(1)
                    continue
                else:
                    print(f"Error fetching data: {response.status}")
                    break
            await self.SESSION.close()


bot.run(os.getenv("DISCORD_TOKEN"))