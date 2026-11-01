"""Create, update and delete a custom agent.

    python examples/16_agents.py

``agents.list`` shows the built-in Cominty agents (``managed=True``) next to your
own. ``agents.create`` builds a custom one from a name, instructions, capabilities
and an optional model chain picked from ``agents.list_models``. ``agents.update``
is partial: only the arguments you pass are sent, ``None`` clears a text or the
capabilities, and a capabilities object is merged key by key. The agent created
here is deleted before the script exits.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import make_client

from cominty_sdk import AgentCapabilities, WebCapability


async def main() -> None:
    async with make_client() as client:
        agents = await client.agents.list()
        builtin = sum(1 for a in agents if a.managed)
        pretty.console.print(f"  [bold]list[/]     {len(agents)} agent(s), {builtin} built in")

        models = await client.agents.list_models()
        pretty.console.print(f"  [bold]models[/]   {', '.join(m.name for m in models[:3])} ...")

        agent = await client.agents.create(
            name="SDK example agent",
            description="Created by examples/16_agents.py",
            instructions="Reply in one short sentence.",
            capabilities=AgentCapabilities(web=WebCapability(activation="never")),
            model_ids=[models[0].id],
        )
        names = [m.name for m in agent.models]
        pretty.console.print(f"  [bold]create[/]   {agent.id} models={names}")

        try:
            # Partial update: the name changes, the description is cleared, the rest stays.
            agent = await client.agents.update(
                agent.id, name="SDK example agent v2", description=None
            )
            pretty.console.print(
                f"  [bold]update[/]   name={agent.name!r} description={agent.description!r}"
            )

            # Merge: web flips to on_request, nothing else in capabilities moves.
            agent = await client.agents.update(
                agent.id, capabilities=AgentCapabilities(web=WebCapability(activation="on_request"))
            )
            assert agent.capabilities is not None and agent.capabilities.web is not None
            pretty.console.print(f"  [bold]merge[/]    web={agent.capabilities.web.activation}")

            if len(models) > 1:
                agent = await client.agents.set_models(
                    agent.id, model_ids=[models[1].id, models[0].id]
                )
                pretty.console.print(f"  [bold]models[/]   {[m.name for m in agent.models]}")

            run = await client.chat.start(agent_id=agent.id, message="Say hello.")
            pretty.answer(await run.text())
        finally:
            await client.agents.delete(agent.id)
            pretty.console.print("  [bold]delete[/]   [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
