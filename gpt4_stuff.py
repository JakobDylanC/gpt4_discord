import openai
import tiktoken
import backoff
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
if "OPENAI_API_KEY" not in os.environ:
    raise ValueError(f"Required environment variable OPENAI_API_KEY is not set.")

GPT4_MODEL = "gpt-4-0613"
GPT4_TOKENS_PER_MESSAGE = 3
GPT4_TOKENS_PER_NAME = 1
GPT4_TOKENS_PER_MESSAGES = 3
GPT4_MAX_TOTAL_TOKENS = 8192
MAX_COMPLETION_TOKENS = 1024 #customize here, must be less than GPT4_MAX_TOTAL_TOKENS
MAX_PROMPT_TOKENS = GPT4_MAX_TOTAL_TOKENS - MAX_COMPLETION_TOKENS - GPT4_TOKENS_PER_MESSAGES
TIMEOUT_SECONDS = 120
openai.api_key = os.environ["OPENAI_API_KEY"]
encoding = tiktoken.get_encoding("cl100k_base")


@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
async def chat_completion(system_prompt, msgs):
    print(f"Generating GPT response for prompt:\n{msgs[-1]['content']}")
    response_content = "Sorry, an error occurred. Please try again."
    try:
        response = await asyncio.wait_for(
            openai.ChatCompletion.acreate(
                model=GPT4_MODEL,
                messages=[system_prompt]+msgs,
                max_tokens=MAX_COMPLETION_TOKENS,
            ), 
            timeout=TIMEOUT_SECONDS
        )
        response_content = response["choices"][0]["message"]["content"].strip()
        print(f"GPT response:\n{response_content}")
        print(f"Prompt tokens: {response['usage']['prompt_tokens']}  Completion tokens: {response['usage']['completion_tokens']}  Total tokens: {response['usage']['total_tokens']}")
    except asyncio.TimeoutError:
        print("Timeout exceeded.")
    return response_content


@backoff.on_exception(backoff.expo, openai.error.RateLimitError)
async def chat_completion_stream(system_prompt, msgs):
    print(f"Generating GPT response for prompt:\n{msgs[-1]['content']}")
    try:
        async for chunk in await asyncio.wait_for(
            openai.ChatCompletion.acreate(
                model=GPT4_MODEL,
                messages=[system_prompt]+msgs,
                max_tokens=MAX_COMPLETION_TOKENS,
                stream=True,
            ), 
            timeout=TIMEOUT_SECONDS
        ):
            delta = chunk["choices"][0].get("delta", {})
            yield delta
    except asyncio.TimeoutError:
        print("Timeout exceeded.")
        yield {}


def count_tokens(msg):
    num_tokens = GPT4_TOKENS_PER_MESSAGE
    for key, value in msg.items():
        num_tokens += len(encoding.encode(value))
        if key == "name":
            num_tokens += GPT4_TOKENS_PER_NAME
    return num_tokens


def split_string_not_words(string, max_length):
    if len(string) <= max_length:
        return [string]
    string_chunks = []
    start_index = 0
    while start_index < len(string):
        end_index = min(start_index+max_length, len(string))
        split_index = string.rfind(" ", start_index, end_index) if end_index < len(string) else end_index
        end_index = split_index if split_index != -1 else end_index
        string_chunks.append(string[start_index:end_index])
        start_index = end_index + 1 if split_index != -1 else end_index
    return string_chunks