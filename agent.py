"""Builds the agent (create_agent) and runs a multi-turn chat: terminal or GUI (app.py).

Token strategy (Groq free tier: 8K tokens/minute, 200K/day, whole chat resent every call):
  * short system prompt + terse tool docs
  * old turns are compacted (long tool results / file contents are clipped)
  * a throttle waits instead of crashing when the minute budget is full
  * rate-limit / malformed-tool-call / network errors are retried; progress is never lost
"""

import json
import re
import time

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

import tools as T
from config import WORK_DIR
from llm import get_llm
from throttle import THROTTLE

SYSTEM_PROMPT = """You are Coding Companion, a careful coding assistant. You work ONLY inside one working folder; all paths are relative to it.

RULES
1. One folder. Use relative paths. Anything outside (.., absolute paths, other drives) is forbidden: refuse and explain. Never write code that reads, writes, lists or deletes outside the folder.
2. Files. You can list, read, create, edit and overwrite files of any type inside the folder.
3. Delete only when the user explicitly asks. delete_file only QUEUES the request; the user must approve it in the UI. Say it is pending, never say it is deleted.
4. Honesty. Never claim you read, wrote, changed, ran, converted, encrypted or deleted anything unless a tool did it in this turn. Report real tool output (including errors) faithfully.
5. Unclear request or missing detail (file name, password, target format): ask ONE short question instead of guessing. Never invent files; list_files if unsure what exists.
6. Create + run: write_file, then execute_file, then show the real output. Edit: read_file, then write_file with the COMPLETE new content, then execute_file again if asked.
7. Be token-efficient: do not re-read files you just wrote, do not repeat file contents in replies unless asked, keep answers short. If a tool fails, fix it once or twice, then explain.
8. Passwords for encrypt/decrypt must come from the user."""

MAX_TURNS_KEPT = 4


# ------------------------------------------------------------------ memory
def _clip(s, n):
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[:n] + f" [...{len(s) - n} chars omitted]"


def _shrink(msg, cap):
    """Return a lighter copy of an old message (long tool output / file content removed)."""
    if isinstance(msg, ToolMessage):
        return msg.model_copy(update={"content": _clip(msg.content, cap)})
    if isinstance(msg, AIMessage) and msg.tool_calls:
        calls = []
        for c in msg.tool_calls:
            args = {
                k: (_clip(v, 120) if isinstance(v, str) and len(v) > 120 else v)
                for k, v in c["args"].items()
            }
            calls.append({**c, "args": args})
        extra = {
            k: v
            for k, v in msg.additional_kwargs.items()
            if k not in ("tool_calls", "reasoning_content")
        }
        return msg.model_copy(update={"tool_calls": calls, "additional_kwargs": extra})
    return msg


def compact(messages, keep_turns=MAX_TURNS_KEPT, cap=500):
    """Keep only the last `keep_turns` user turns; clip big content in all but the newest turn."""
    humans = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if not humans:
        return list(messages)
    start = humans[-keep_turns] if len(humans) > keep_turns else 0
    last = humans[-1]
    return [
        (_shrink(m, cap) if i < last else m)
        for i, m in enumerate(messages)
        if i >= start
    ]


# ------------------------------------------------------------------- agent
def build_agent():
    return create_agent(model=get_llm(), tools=T.TOOLS, system_prompt=SYSTEM_PROMPT)


def _classify(e: Exception):
    msg = str(e).lower()
    status = getattr(e, "status_code", None)
    if status == 401 or "invalid api key" in msg:
        return "auth", 0
    if status == 429 or "rate limit" in msg or "rate_limit" in msg:
        if "per day" in msg or "tpd" in msg:
            return "daily", 0
        m = re.search(r"try again in\s+(?:(\d+)m)?\s*(?:(\d+(?:\.\d+)?)s)?", msg)
        wait = (int(m.group(1) or 0) * 60 + float(m.group(2) or 0)) if m else 0
        return "rate", min(max(wait + 1, 5), 90)
    if status == 413 or "request too large" in msg or "reduce your message size" in msg:
        return "toolarge", 0
    if (
        "tool_use_failed" in msg
        or "failed to call a function" in msg
        or "failed_generation" in msg
    ):
        return "toolfail", 0
    if "recursion" in type(e).__name__.lower() or "recursion limit" in msg:
        return "steps", 0
    if (isinstance(status, int) and status >= 500) or any(
        w in msg
        for w in ("timeout", "timed out", "connection", "overloaded", "temporarily")
    ):
        return "transient", 4
    return "fatal", 0


def _events_for(m):
    """Turn one new message into GUI/terminal events."""
    if isinstance(m, AIMessage):
        for c in m.tool_calls:
            yield {"type": "tool_call", "name": c["name"], "args": c["args"]}
    elif isinstance(m, ToolMessage):
        yield {
            "type": "tool_result",
            "name": m.name or "tool",
            "content": str(m.content),
        }


class Companion:
    def __init__(self):
        self.agent = build_agent()
        self.history: list = []
        THROTTLE.tool_overhead = (
            int(sum(len(json.dumps(convert_to_openai_tool(t))) for t in T.TOOLS) / 3.2)
            + 150
        )

    def reset(self):
        self.history = []

    def note(self, text: str, reply: str):
        """Record something that happened outside the agent (e.g. the user approved a delete)."""
        self.history += [HumanMessage(content=text), AIMessage(content=reply)]

    def chat(self, user_text: str):
        """Generator of events: tool_call, tool_result, status, assistant, error."""
        state = compact(self.history) + [HumanMessage(content=user_text)]
        seen = len(state)
        latest = state
        tries = {"rate": 0, "transient": 0, "toolfail": 0, "toolarge": 0}
        config = {"callbacks": [THROTTLE], "recursion_limit": 30}

        def resume_point(msgs):
            msgs = list(msgs)
            while msgs and isinstance(msgs[-1], AIMessage) and msgs[-1].tool_calls:
                msgs.pop()  # a tool call that never got its result cannot be resent
            return msgs

        while True:
            try:
                for chunk in self.agent.stream(
                    {"messages": state}, config=config, stream_mode="values"
                ):
                    msgs = chunk["messages"]
                    for m in msgs[seen:]:
                        yield from _events_for(m)
                    seen = max(seen, len(msgs))
                    latest = msgs
                break
            except Exception as e:  # noqa: BLE001
                kind, wait = _classify(e)
                state = resume_point(latest)
                seen = len(state)
                if kind == "rate" and tries["rate"] < 4:
                    tries["rate"] += 1
                    yield {
                        "type": "status",
                        "text": f"Groq rate limit reached - waiting {wait:.0f}s, then continuing (progress is kept).",
                    }
                    THROTTLE.wait_for(wait)
                    continue
                if kind == "transient" and tries["transient"] < 3:
                    tries["transient"] += 1
                    yield {
                        "type": "status",
                        "text": "Temporary network/server problem - retrying.",
                    }
                    time.sleep(wait * tries["transient"])
                    continue
                if kind == "toolfail" and tries["toolfail"] < 2:
                    tries["toolfail"] += 1
                    yield {
                        "type": "status",
                        "text": "The model made a malformed tool call - asking it to retry.",
                    }
                    state = state + [
                        HumanMessage(
                            content="Your last tool call was malformed. Retry with valid JSON arguments."
                        )
                    ]
                    seen = len(state)
                    continue
                if kind == "toolarge" and tries["toolarge"] < 1:
                    tries["toolarge"] += 1
                    yield {
                        "type": "status",
                        "text": "Conversation too big for one request - trimming older context.",
                    }
                    state = compact(state, keep_turns=1, cap=200)
                    seen = len(state)
                    continue
                reasons = {
                    "auth": "The API key was rejected. Check `API_KEY` in your .env file.",
                    "daily": "Groq's daily token limit (200K) is used up. Try again later (it resets daily).",
                    "steps": "I hit my step limit for one request. Your files so far are saved; tell me to continue.",
                    "toolarge": "This request is too big for Groq's per-minute limit. Start a New chat and try again.",
                }
                text = reasons.get(
                    kind,
                    f"Stopped because of an error: {type(e).__name__}: {_clip(e, 300)}",
                )
                yield {"type": "error", "text": text}
                self.history = state + [AIMessage(content=f"(Stopped: {text})")]
                return

        final = next(
            (
                m
                for m in reversed(latest)
                if isinstance(m, AIMessage) and not m.tool_calls
            ),
            None,
        )
        text = (
            final.content if final and isinstance(final.content, str) else ""
        ).strip() or "(The model returned no text.)"
        self.history = latest
        yield {"type": "assistant", "text": text}


# ---------------------------------------------------------------- terminal
def run_terminal():
    print(
        f"Coding Companion - working folder: {WORK_DIR}\nType 'exit' to quit, 'new' for a fresh chat.\n"
    )
    THROTTLE.on_wait = lambda s: (
        print(f"  ... waiting {s:.0f}s (rate limit)", end="\r") if s > 0 else None
    )
    bot = Companion()
    while True:
        try:
            q = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            break
        if q.lower() == "new":
            bot.reset()
            print("(new chat)")
            continue
        for ev in bot.chat(q):
            if ev["type"] == "tool_call":
                print(
                    f"  [tool] {ev['name']}({_clip(json.dumps(ev['args'], ensure_ascii=False), 100)})"
                )
            elif ev["type"] == "tool_result":
                print(f"  [result] {_clip(ev['content'], 200)}")
            elif ev["type"] in ("status", "error"):
                print(f"  ! {ev['text']}")
            else:
                print(f"\nagent > {ev['text']}\n")
        for item in list(T.PENDING_DELETES):
            ok = (
                input(f"Delete {item['kind']} '{item['rel']}'? [y/N] ").strip().lower()
                == "y"
            )
            result = T.resolve_delete(item, ok)
            print(result)
            bot.note(f"[user decision] {result}", "Understood.")


if __name__ == "__main__":
    import config

    issues = config.problems()
    if issues:
        raise SystemExit("Fix .env first:\n- " + "\n- ".join(issues))
    run_terminal()
