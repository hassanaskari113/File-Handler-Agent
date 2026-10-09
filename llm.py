"""The model. Tested model: groq:openai/gpt-oss-120b."""

from functools import lru_cache

from langchain_groq import ChatGroq

from config import API_KEY, MAX_OUTPUT_TOKENS, MODEL


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    return ChatGroq(
        model=MODEL,
        api_key=API_KEY,
        temperature=0,
        max_tokens=MAX_OUTPUT_TOKENS,  # smaller reserve = fewer rate-limit problems
        reasoning_effort="low",  # gpt-oss: less hidden reasoning = fewer tokens
        max_retries=1,  # our own recovery loop in agent.py does the rest
        timeout=60,
    )
