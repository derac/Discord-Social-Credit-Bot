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
        # these models have what we need and have the largest context
        # https://openrouter.ai/models?order=newest&supported_parameters=structured_outputs&max_price=0
        self.MODELS = ["openai/gpt-oss-20b:free", "qwen/qwen3-235b-a22b:free"]
        self.bot = bot
        self.logger = logger
        self.session = aiohttp.ClientSession()
        self.SCAN_PERIOD = timedelta(hours=1)
        self.SYSTEM_PROMPT = "You are a discord bot which seeks to assign a social credit score to all users in \
a discord server based on the history of their messages from the past day. I will also provide the current \
data for each user, including their total score and the previous reasoning given. Good behavior should \
score well, while bad behavior should score poorly. Provide output as json. When writing reasoning \
for the score you've given someone, include any information from the last output that you want to retain. \
This is the only place you can store memories about a user. Roast the bad users, praise the good users. \
Make it fun and funny if appropriate. The social credit score should be between -100 and 100, it will be \
added to the user's current social credit score. If the user's score is negative, they will be put into a \
bad person group, if it's positive, they will be a good person. Only good people are allowed to chat in good \
person chat."

        self.USER_SCHEMA = {
            "type": "object",
            "required": ["social_credit_modifier", "reasoning"],
            "properties": {
                "social_credit_modifier": {
                    "type": "number",
                    "description": "A number that will be used to modify the total social credit of the user..",
                    "minimum": -100,
                    "maximum": 100,
                },
                "reasoning": {
                    "type": "string",
                    "description": "Reasoning for your score.",
                },
            },
            "additionalProperties": False,
        }
        self.USER_DATA_PATH = "social_credit_data.json"
        self.USER_DATA = dict()
        if os.path.exists(self.USER_DATA_PATH):
            with open(self.USER_DATA_PATH) as file:
                self.USER_DATA = json.loads(file.read())

    @commands.command()
    async def judge(self, ctx):
        if ctx.author.id != int(os.getenv("AUTHORIZED_USER_ID")):
            await ctx.send("You are not authorized to use this command.")
            return
        message_log = ""
        user_list = set()

        for channel in ctx.guild.text_channels:
            if channel.name in ["bad-people", "good-people"]:
                message_log += f"\n# Channel - {channel.name.capitalize()}\n"
                async for message in channel.history():
                    message_time_difference = (
                        datetime.now(timezone.utc) - message.created_at
                    )
                    if message_time_difference < self.SCAN_PERIOD:
                        message_log += f"{message.author.name}: {message.content}\n"
                        user_list.add(message.author.name)
                    else:
                        break
        user_list = list(user_list)
        prompt = f"{message_log}\n\n# Current data on users\n\n{self.USER_DATA}"
        self.logger.debug(f"Fetched a message log of length {len(message_log)}")
        self.logger.debug(f"{len(user_list)} users: {user_list}")
        self.logger.debug(f"Prompt length: {len(prompt)}")
        schema_properties = {str(user): self.USER_SCHEMA for user in user_list}
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "Social Credit scores and reasoning for them for all users",
                "strict": True,
                "schema": {
                    "type": "object",
                    "required": [str(user) for user in user_list],
                    "properties": schema_properties,
                    "additionalProperties": False,
                },
            },
        }
        prompt_config = {
            "models": self.MODELS,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "provider": {
                "order": ["atlas-cloud/fp8", "atlas-cloud/fp8"],
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
                    await self.process_ai_response(ctx, data)
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
        await self.create_discord_objects(
            ctx=ctx, names=["Bad person", "Good person"], object_type="role"
        )
        await self.create_discord_objects(
            ctx=ctx, names=["Social Credit Simulator"], object_type="category"
        )
        await self.create_discord_objects(
            ctx=ctx, names=["bad-people", "good-people"], object_type="text_channel"
        )

    async def create_discord_objects(
        self,
        ctx,
        names: list[str],
        object_type: Literal["role", "text_channel", "category"],
    ) -> list:
        object_type_plural = (
            f"{object_type[0:-1]+'ie' if object_type[-1]=='y' else object_type}s"
        )
        object_type_capitalized = object_type.capitalize()
        create_object_function = getattr(ctx.guild, f"create_{object_type}")
        existing_objects = getattr(ctx.guild, object_type_plural)
        objects = []
        for name in names:
            if not discord.utils.get(existing_objects, name=name):
                try:
                    objects.append(
                        await create_object_function(
                            name=name,
                            reason=f"{object_type_capitalized} created by bot as it didn't exist.",
                        )
                    )
                    await ctx.send(
                        f"{object_type_capitalized} '{name}' created successfully."
                    )
                except discord.Forbidden:
                    await ctx.send(
                        "I don't have permission to create {object_type_plural}."
                    )
                except Exception as e:
                    await ctx.send(
                        f"An error occurred while creating the {object_type}: {e}"
                    )
            else:
                await ctx.send(f"The {object_type} {name} already exists.")
        return objects

    async def process_ai_response(self, ctx, data):
        self.logger.debug(data)
        raw_json_response = data["choices"][0]["message"]["content"]
        social_credit_data = json.loads(raw_json_response)
        #self.logger.debug(social_credit_data)
        #self.logger.debug(self.USER_DATA)
        output = ""
        for user, data in social_credit_data.items():
            if user not in self.USER_DATA:
                self.USER_DATA[user] = {}
                self.USER_DATA[user]["social_credit_score"] = 0
            self.USER_DATA[user]["social_credit_score"] += int(
                data["social_credit_modifier"]
            )
            self.USER_DATA[user]["reasoning"] = data["reasoning"]
            if "-" not in str(data["social_credit_modifier"]):
                data["social_credit_modifier"] = f"+{data['social_credit_modifier']}"
            output += f"{user}\n{self.USER_DATA[user]['social_credit_score']} ({data["social_credit_modifier"]})\n{self.USER_DATA[user]['reasoning']}\n\n"
        with open(self.USER_DATA_PATH, "w") as file:
            file.write(json.dumps(self.USER_DATA, indent=4))
        await ctx.send(output)

        bad_role = discord.utils.get(ctx.guild.roles, name="Bad person")
        good_role = discord.utils.get(ctx.guild.roles, name="Good person")
        for user, data in self.USER_DATA.items():
            user_object = discord.utils.get(ctx.guild.members, name=user)
            if data["social_credit_score"] > 0:
                await user_object.add_roles(good_role)
                await user_object.remove_roles(bad_role)
            else:
                await user_object.remove_roles(good_role)
                await user_object.add_roles(bad_role)