import gpt4_stuff
import discord
import asyncio
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()
REQUIRED_ENV_VARS = ["DISCORD_BOT_TOKEN", "CUSTOM_SYSTEM_PROMPT"]
if (missing_env_vars := [var for var in REQUIRED_ENV_VARS if var not in os.environ]):
    raise ValueError(f"Required environment variables are not set: {', '.join(missing_env_vars)}")

DISCORD_MSG_LENGTH_LIMIT = 2000
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
in_progress_message_ids = []

class MsgNode:
    def __init__(self, msg, reply_to=None):
        self.msg = msg
        self.tokens = gpt4_stuff.count_tokens(msg)
        self.reply_to = reply_to

    def get_reply_chain(self, system_prompt_tokens):
        chain = []
        num_tokens = system_prompt_tokens
        current_msg = self
        while current_msg != None:
            num_tokens += current_msg.tokens
            if num_tokens > gpt4_stuff.MAX_PROMPT_TOKENS:
                break
            chain.append(current_msg.msg)
            current_msg = current_msg.reply_to
        print(f"Calculated prompt tokens: {num_tokens + gpt4_stuff.GPT4_TOKENS_PER_MESSAGES}")
        return chain[::-1]
msg_nodes = {}

@bot.event
async def on_message(message):
    if bot.user not in message.mentions or message.author.bot:
        return

    user_prompt_content = message.content.replace(bot.user.mention, "", 1).strip()
    if not user_prompt_content:
        return
    
    while message.reference and message.reference.message_id in in_progress_message_ids:
        await asyncio.sleep(0)
    
    async with message.channel.typing():
        msg_nodes[message.id] = MsgNode({"role": "user", "content": user_prompt_content, "name": str(message.author.id)})
        if message.reference and message.reference.message_id in msg_nodes:
            msg_nodes[message.id].reply_to = msg_nodes[message.reference.message_id]
        elif message.reference:
            try:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg.content:
                    author_role = "assistant" if ref_msg.author == bot.user else "user"
                    msg_nodes[ref_msg.id] = MsgNode({"role": author_role, "content": ref_msg.content, "name": str(ref_msg.author.id)})
                    msg_nodes[message.id].reply_to = msg_nodes[ref_msg.id]
            except discord.DiscordException:
                print("Error fetching the referenced message")

        current_date = datetime.now().strftime("%B %d, %Y")
        system_prompt_content = f"{os.environ['CUSTOM_SYSTEM_PROMPT']}\nKnowledge cutoff: Sep 2021. Current date: {current_date}"
        system_prompt = {"role": "system", "content": system_prompt_content}
        system_prompt_tokens = gpt4_stuff.count_tokens(system_prompt)
        msgs = msg_nodes[message.id].get_reply_chain(system_prompt_tokens)
        if not msgs: return
        response_messages = []
        response = ""
        edit_message_task = None
        previous_delta = None
        async for current_delta in gpt4_stuff.chat_completion_stream(system_prompt, msgs):
            if previous_delta != None:
                current_delta_content = current_delta.get("content", "")
                previous_delta_content = previous_delta.get("content", "")
                if previous_delta_content != "":
                    if response_messages == [] or len(response_message_content+previous_delta_content) > DISCORD_MSG_LENGTH_LIMIT:
                        response_messages.append(await message.reply(content=previous_delta_content))
                        in_progress_message_ids.append(response_messages[-1].id)
                        response_message_content = ""
                    response_message_content += previous_delta_content
                    response += previous_delta_content
                    if edit_message_task is None or edit_message_task.done() or len(response_message_content+current_delta_content) > DISCORD_MSG_LENGTH_LIMIT or current_delta == {}:
                        while isinstance(edit_message_task, asyncio.Task) and not edit_message_task.done():
                            await asyncio.sleep(0)
                        edit_message_task = asyncio.create_task(response_messages[-1].edit(content=response_message_content))
            previous_delta = current_delta
        for response_message in response_messages:
            msg_nodes[response_message.id] = MsgNode({"role": "assistant", "content": response}, reply_to=msg_nodes[message.id])
            in_progress_message_ids.remove(response_message.id)

async def main():
    await bot.start(os.environ["DISCORD_BOT_TOKEN"])

if __name__ == "__main__":
    asyncio.run(main())