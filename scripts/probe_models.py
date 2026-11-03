"""Phase 0 probe: list the models the configured key can use and smoke-test tool calling.

Usage:
    python scripts/probe_models.py            # list models only
    python scripts/probe_models.py MODEL ...  # also test chat + tool call on each MODEL
    python scripts/probe_models.py --embed MODEL  # test an embedding model
"""
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
    max_retries=0,  # surface rate-limit errors instead of hiding them behind SDK retries
)

# The probe asks something only a tool can answer, so a plain-text reply means no tool calling.
PRICE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_price",
        "description": "Return the current price of a product in BRL.",
        "parameters": {
            "type": "object",
            "properties": {"product": {"type": "string"}},
            "required": ["product"],
        },
    },
}


def probe_chat(model: str) -> None:
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[{"role": "user", "content": "Quanto custa o Takamine GD20?"}],
            tools=[PRICE_TOOL],
        )
    except Exception as exc:  # report every failure mode (404, 429, 400) verbatim
        print(f"  {model}: FAILED {type(exc).__name__}: {str(exc)[:200]}")
        return
    calls = resp.choices[0].message.tool_calls or []
    names = [(c.function.name, c.function.arguments) for c in calls]
    print(f"  {model}: ok in {time.time() - start:.1f}s, tool_calls={names}")


def probe_embed(model: str) -> None:
    try:
        resp = client.embeddings.create(model=model, input=["horário de funcionamento"])
        print(f"  {model}: ok, dim={len(resp.data[0].embedding)}")
    except Exception as exc:
        print(f"  {model}: FAILED {type(exc).__name__}: {str(exc)[:200]}")


def main(args: list[str]) -> None:
    if args and args[0] == "--embed":
        for m in args[1:]:
            probe_embed(m)
        return
    ids = sorted(m.id for m in client.models.list())
    print(f"{len(ids)} models available:")
    for i in ids:
        print(" ", i)
    for m in args:
        probe_chat(m)


if __name__ == "__main__":
    main(sys.argv[1:])
