"""This is a module for creating a SocialCredit bot. It sets up a game where
it reads messages and assigns social credit scores to users in your chat. These
scores determine roles that apply priveleges and restrictions.

It creates two roles and two chats, bad and good. After judgement users are sorted
by whether their social credit score is positive or negative.
"""

import os, json, time
from datetime import datetime, timedelta, timezone
from typing import Literal

import aiohttp, discord
from discord.ext import commands
from dotenv import load_dotenv


class SocialCredit(commands.Cog):
    def __init__(self, bot, logger):
        load_dotenv()
        #self.config = SocialCreditConfig()
        self.bot = bot
        self.logger = logger
        self.session = aiohttp.ClientSession()
        # these models have what we need and have the largest context
        # https://openrouter.ai/models?order=newest&supported_parameters=structured_outputs&max_price=0
        self.MODELS = ["qwen/qwen3-235b-a22b:free", "google/gemma-3-27b-it:free"]
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
        if ctx.author.id != int(os.getenv("AUTHORIZED_USER_ID")):
            await ctx.send("You are not authorized to use this command.")
            return
        all_channel_message_log = ""
        all_users_with_messages = set()

        for channel in ctx.guild.text_channels:
            if channel.name in ["bad-people", "good-people"]:
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
        # self.logger.debug(all_channel_message_log)
        self.logger.debug(
            f"Fetched a message log of length {len(all_channel_message_log)}"
        )
        self.logger.debug(
            f"{len(all_users_with_messages)} users: {all_users_with_messages}"
        )
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
                "max_price": {"prompt": 0, "completion": 0},
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
            async with self.session.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                data=json.dumps(prompt_config),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    self.logger.debug(data)
                    social_credit_scores = json.loads(
                        data["choices"][0]["message"]["content"]
                    )
                    self.logger.debug(social_credit_scores)
                    output = ""
                    for user, data in social_credit_scores.items():
                        social_credit_score = data["social_credit_score"]
                        reasoning = data["reasoning"]
                        output += f"{user} ({social_credit_score})\n{reasoning}\n\n"
                    await ctx.send(output)
                    break
                elif response.status == 429:
                    self.logger.debug(f"Error {response.status} - Retrying in 1s")
                    time.sleep(1)
                    continue
                else:
                    self.logger.debug(
                        f"Error fetching data: {response.status} - {response}"
                    )
                    break
            await self.session.close()

    # TODO: replace data here with config objects that allow the user to set names and permissions etc granularly.
    @commands.command()
    async def setup(self, ctx):
        guild = ctx.guild
        await self.create_discord_objects(ctx=ctx, names=["Bad person", "Good person"], object_type="role")
        await self.create_discord_objects(ctx=ctx, names=["Social Credit Simulator"], object_type="category")
        await self.create_discord_objects(ctx=ctx, names=["bad-people", "good-people"], object_type="text_channel")

    async def create_discord_objects(self, ctx, names: list[str], object_type: Literal["role", "text_channel", "category"]) -> None:
        object_type_plural = f"{object_type[0:-1]+'ie' if object_type[-1]=='y' else object_type}s"
        object_type_capitalized = object_type.capitalize()
        create_object_function = getattr(ctx.guild, f"create_{object_type}")
        existing_objects = getattr(ctx.guild, object_type_plural)
        for name in names:
            if not discord.utils.get(existing_objects, name=name):
                try:
                    await create_object_function(
                        name=name, reason=f"{object_type_capitalized} created by bot as it didn't exist."
                    )
                    await ctx.send(f"{object_type_capitalized} '{name}' created successfully.")
                except discord.Forbidden:
                    await ctx.send("I don't have permission to create {object_type_plural}.")
                except Exception as e:
                    await ctx.send(f"An error occurred while creating the {object_type}: {e}")
            else:
                await ctx.send(f"The {object_type} {name} already exists.")