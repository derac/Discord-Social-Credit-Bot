import os, json, time
from datetime import datetime, timedelta, timezone

import aiohttp, discord
from discord.ext import commands
from dotenv import load_dotenv


class SocialCredit(commands.Cog):
    def __init__(self, bot, LOGGER):
        load_dotenv()
        self.bot = bot
        self.LOGGER = LOGGER
        # these models have what we need and have the largest context
        # https://openrouter.ai/models?order=newest&supported_parameters=structured_outputs&max_price=0
        self.MODELS = ["qwen/qwen3-235b-a22b:free","google/gemma-3-27b-it:free"]#["qwen/qwen3-235b-a22b:free","meta-llama/llama-3.1-405b-instruct:free","google/gemma-3-27b-it:free", ]
        self.SESSION = aiohttp.ClientSession()
        self.SCAN_PERIOD = timedelta(hours=1)
        self.SYSTEM_PROMPT = "You are a discord bot which seeks to assign a social credit score to all users in \
        a discord server based on the history of their messages from the past day. Good behavior should \
        score well, while bad behavior should score poorly. Provide output as json. When writing reasoning \
        for the score you've given someone, make it concise and matter of fact. Speak like an impersonal \
        robot social credit system that looms over the chat and judges from on high."
        self.USER_SCHEMA = {
            "type": "object",
            "required": ["social_credit_score", "reasoning"],
            "properties": {
                "social_credit_score": {
                    "type": "number",
                    "description": "A social credit score for this user. A number between -100 and 100",
                    "minimum": -100,
                    "maximum": 100,
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning for giving this user this score.",
                },
            },
            "additionalProperties": False,
        }


    @commands.command()
    async def judge(self, ctx):
        AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
        if ctx.author.id != AUTHORIZED_USER_ID:
            await ctx.send("You are not authorized to use this command.")
            return
        all_channel_message_log = ""
        all_users_with_messages = set()

        for channel in ctx.guild.text_channels:
            if channel.name in ["bad-people","good-people"]:
                all_channel_message_log += (
                    f"\n# Channel - {channel.name.capitalize()}\n"
                )
                async for message in channel.history():
                    message_time_difference = (
                        datetime.now(timezone.utc) - message.created_at
                    )
                    if message_time_difference < self.SCAN_PERIOD:
                        all_channel_message_log += (
                            f"{message.author.name}: {message.content}\n"
                        )
                        all_users_with_messages.add(message.author.name)
                    else:
                        break
        all_users_with_messages = list(all_users_with_messages)
        #self.LOGGER.debug(all_channel_message_log)
        self.LOGGER.debug(f"Fetched a message log of length {len(all_channel_message_log)}")
        self.LOGGER.debug(f"{len(all_users_with_messages)} users: {all_users_with_messages}")
        schema_properties = dict()
        for user in all_users_with_messages:
            schema_properties[str(user)] = self.USER_SCHEMA
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "Social Credit scores and reasoning for them for all users",
                "strict": True,
                "schema": {
                    "type": "object",
                    "required": [str(user) for user in all_users_with_messages],
                    "properties": schema_properties,
                    "additionalProperties": False,
                },
            },
        }
        prompt_config = {
            "models": self.MODELS,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": all_channel_message_log},
            ],
            "provider": {
                "order": ["venice/fp8", "google-ai-studio"],
                "allow_fallbacks": True,
                "sort": "latency",
                "data_collection": "deny",
                "require_parameters": True,
                "max_price": {"prompt": 0, "completion": 0}
            },
            "response_format": response_format,
            # "temperature": 0.7,
            # "top_p": 1,
            # "frequency_penalty": 0,
            # "presence_penalty": 0,
            # "max_tokens": 10,
        }
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_KEY')}",
            "Content-Type": "application/json",
        }

        while True:
            async with self.SESSION.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(prompt_config),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.LOGGER.debug(data)
                    social_credit_scores = json.loads(
                        data["choices"][0]["message"]["content"]
                    )
                    self.LOGGER.debug(social_credit_scores)
                    output = ""
                    for user, data in social_credit_scores.items():
                        social_credit_score = data["social_credit_score"]
                        reasoning = data["reasoning"]
                        output += f"{user} ({social_credit_score})\n{reasoning}\n\n"
                    await ctx.send(output)
                    break
                elif response.status == 429:
                    self.LOGGER.debug(f"Error {response.status} - Retrying in 1s")
                    time.sleep(1)
                    continue
                else:
                    self.LOGGER.debug(f"Error fetching data: {response.status} - {response}")
                    break
            await self.SESSION.close()

    @commands.command()
    async def setup(self, ctx):
        guild = ctx.guild
        for role in ["Bad person","Good person"]:
            if not discord.utils.get(guild.roles, name=role):
                try:
                    await guild.create_role(name=role, reason="Role created by bot as it didn't exist.")
                    await ctx.send(f"Role '{role}' created successfully.")
                except discord.Forbidden:
                    await ctx.send("I don't have permission to create roles.")
                except Exception as e:
                    await ctx.send(f"An error occurred while creating the role: {e}")
            else:
                await ctx.send(f"The role {role} already exists.")
        category = "Social Credit Simulator"
        if not discord.utils.get(guild.categories, name=category):
            try:
                await guild.create_category(category)
                await ctx.send(f"Category '{category}' created successfully.")
            except discord.Forbidden:
                await ctx.send("I don't have permission to create categories.")
            except Exception as e:
                await ctx.send(f"An error occurred while creating the category: {e}")
        else:
            await ctx.send(f"The category {category} already exists.")
        for channel in ["bad-people","good-people"]:
            if not discord.utils.get(guild.text_channels, name=channel):
                try:
                    await guild.create_text_channel(channel, category=discord.utils.get(guild.categories, name=category))
                    await ctx.send(f"Channel '{channel}' created successfully.")
                except discord.Forbidden:
                    await ctx.send("I don't have permission to create channels.")
                except Exception as e:
                    await ctx.send(f"An error occurred while creating the channel: {e}")
            else:
                await ctx.send(f"The channel {channel} already exists.")