"""Answer an agent's clarifying questions.

    python examples/04_answer_questions.py

When an agent needs more input, it ends its turn with one or more questions
(``prompt`` + suggested ``options``) instead of a final answer. Read them with
``run.questions()``, then answer by sending the chosen option (or free text) as
the next message in the thread — exactly like any other follow-up.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import AGENT_ID, make_client


async def main() -> None:
    async with make_client() as client:
        run = await client.chat.start(
            agent_id=AGENT_ID,
            message="Book me a meeting room.",  # deliberately under-specified
        )
        await run.text()  # drain to completion

        questions = await run.questions()
        if not questions:
            pretty.answer(await run.text())  # agent answered directly
            return

        # A real app would present these to the user. Here we auto-pick option 0.
        q = questions[0]
        pretty.console.print(f"  [bold]Agent asks:[/] {q.prompt}")
        pretty.console.print(f"  [dim]options:[/] {q.options}")
        chosen = q.options[0] if q.options else "Tomorrow at 10am"
        pretty.console.print(f"  [green]→ answering:[/] {chosen!r}")

        followup = await client.chat.send(
            run.thread.id, agent_id=AGENT_ID, message=chosen
        )
        pretty.answer(await followup.text())


if __name__ == "__main__":
    asyncio.run(main())
