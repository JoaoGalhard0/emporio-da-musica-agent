"""Test doubles shared by the agent and CLI tests."""
import json


class ScriptedLLM:
    """Returns the queued assistant messages in order and records what it was sent."""

    model = "scripted"

    def __init__(self, *messages):
        self.queue = list(messages)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.2):
        self.calls.append(list(messages))
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def say(text):
    return {"role": "assistant", "content": text}


def call(name, args, call_id="c1"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}
