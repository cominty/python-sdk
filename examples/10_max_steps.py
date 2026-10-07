"""Cap the agent's tool rounds with ``max_steps``, then continue past the cap.

    python examples/10_max_steps.py

``max_steps`` limits how many tool rounds (web search, file write, ...) the agent
may run for ONE message. Reaching the cap is not an error: the agent stops using
tools, replies with a short recap, and asks whether to continue. The message ends
with ``status="success"``; no field flags that the cap was hit, and the wording is
written by the model, so never parse the reply text.

Rules to remember:
- The cap is per message, not per thread. A follow-up that leaves ``max_steps``
  unset runs with the server default (60 today), whatever the first message used.
  Pass an integer on every call to keep a custom cap.
- Leaving it unset (or passing ``SERVER_DEFAULT``) omits the field from the
  request. There is no "unlimited": ``None`` and integers below 1 raise
  ``InvalidParams`` locally.
- It is a rough order of magnitude, not an exact count: the agent can run up to
  ``max_steps + 1`` rounds, and each sub-agent gets its own budget.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client

from cominty_sdk import SERVER_DEFAULT, InvalidParams

TASK = (
    "1. Search the web for what is new in Python 3.13. "
    "2. Read the most relevant page. "
    "3. Write a short summary of it in your reply."
)


async def main() -> None:
    async with make_client() as client:
        # A deliberately tight cap: the task above needs more than one round.
        first = await client.chat.start(agent_id=AGENT_ID, message=TASK, max_steps=1)
        pretty.rule("Turn 1: max_steps=1")
        pretty.answer(await first.text())
        reply = await first.result()
        # Hitting the cap still ends in "success": this is not a failure.
        pretty.console.print(f"  [dim]status[/] {reply.status.value}")

        # Answer the agent's "do you want me to continue?" with a bigger budget.
        # The new message gets its own cap; nothing is inherited from turn 1.
        second = await client.chat.send(
            first.thread.id,
            agent_id=AGENT_ID,
            message="Yes, continue.",
            max_steps=10,
        )
        pretty.rule("Turn 2: max_steps=10")
        pretty.answer(await second.text())

        # Explicit server default: same as omitting the argument.
        third = await client.chat.send(
            first.thread.id,
            agent_id=AGENT_ID,
            message="Now give it to me in one sentence.",
            max_steps=SERVER_DEFAULT,
        )
        pretty.rule("Turn 3: server default")
        pretty.answer(await third.text())

        # Invalid values are rejected before any request is sent.
        try:
            await client.chat.start(agent_id=AGENT_ID, message="hi", max_steps=0)
        except InvalidParams as exc:
            pretty.rule("Invalid value")
            pretty.console.print(f"  [red]{exc}[/]")


if __name__ == "__main__":
    asyncio.run(main())
