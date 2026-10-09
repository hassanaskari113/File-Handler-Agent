"""Keeps the agent under Groq's free-tier limit (8K tokens/minute) and counts usage.

Every model call resends the whole conversation, so before each call we estimate its
size and, if the last 60 seconds are too full, wait instead of crashing mid-task.
"""

import time
from collections import deque

from langchain_core.callbacks import BaseCallbackHandler

TPM_LIMIT = 7000  # stay below Groq's 8000 tokens/minute
OUTPUT_RESERVE = 700  # typical reply size we reserve room for


class TokenThrottle(BaseCallbackHandler):
    def __init__(self):
        self.events: deque = deque()  # (timestamp, tokens)
        self.total = 0  # tokens used this session
        self.calls = 0
        self.tool_overhead = (
            2500  # estimated size of the tool schemas (set by agent.py)
        )
        self.on_wait = None  # optional callback(seconds_left) for the GUI

    # -- helpers -----------------------------------------------------------
    def _used_last_minute(self) -> int:
        cutoff = time.time() - 60
        while self.events and self.events[0][0] < cutoff:
            self.events.popleft()
        return sum(t for _, t in self.events)

    def wait_for(self, seconds: float):
        """Sleep (in 1s steps so the GUI can show a countdown)."""
        end = time.time() + seconds
        while (left := end - time.time()) > 0:
            if self.on_wait:
                self.on_wait(left)
            time.sleep(min(1.0, left))
        if self.on_wait:
            self.on_wait(0)

    # -- LangChain callbacks ----------------------------------------------
    def on_chat_model_start(self, serialized, messages, **kwargs):
        chars = 0
        for batch in messages:
            for m in batch:
                chars += len(str(m.content)) + len(str(getattr(m, "tool_calls", "")))
        need = int(chars / 3.2) + self.tool_overhead + OUTPUT_RESERVE
        while self.events:
            used = self._used_last_minute()
            if used + need <= TPM_LIMIT or not self.events:
                break
            self.wait_for(max(1.0, self.events[0][0] + 60 - time.time() + 0.5))

    def on_llm_end(self, response, **kwargs):
        tokens = 0
        try:
            u = response.generations[0][0].message.usage_metadata or {}
            tokens = u.get("total_tokens") or (
                u.get("input_tokens", 0) + u.get("output_tokens", 0)
            )
        except Exception:
            try:
                tokens = (
                    (response.llm_output or {})
                    .get("token_usage", {})
                    .get("total_tokens", 0)
                )
            except Exception:
                tokens = 0
        if tokens:
            self.events.append((time.time(), tokens))
            self.total += tokens
        self.calls += 1


THROTTLE = TokenThrottle()
