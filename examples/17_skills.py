"""Upload a skill folder and attach it to an agent.

    python examples/17_skills.py

A skill is a folder with a ``SKILL.md`` whose YAML frontmatter follows the
agentskills.io specification (``name``, ``description``, ...), plus any supporting
files. ``skills.create`` zips the folder in memory and the server parses the
frontmatter. The skill then goes to an agent through
``SkillsCapability(include=[skill.id])``. Both are deleted before the script exits.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import _pretty as pretty
from _shared import make_client

from cominty_sdk import AgentCapabilities, SkillsCapability

SKILL_MD = """---
name: haiku-answers
description: Answer every question as a haiku, three lines of five, seven and five syllables.
---

When the user asks anything, reply with a single haiku and nothing else.
"""


async def main() -> None:
    folder = Path(tempfile.mkdtemp(prefix="cominty-skill-")) / "haiku-answers"
    folder.mkdir()
    (folder / "SKILL.md").write_text(SKILL_MD)

    async with make_client() as client:
        skill = await client.skills.create(folder, display_name="SDK example: haiku answers")
        pretty.console.print(
            f"  [bold]create[/]   {skill.id} name={skill.frontmatter.name!r} "
            f"source={skill.source.value}"
        )

        agent = None
        try:
            skill = await client.skills.update(skill.id, display_name="SDK example: haiku")
            pretty.console.print(f"  [bold]update[/]   display_name={skill.display_name!r}")

            agent = await client.agents.create(
                name="SDK example haiku agent",
                capabilities=AgentCapabilities(
                    skills=SkillsCapability(activation="always", include=[skill.id])
                ),
            )
            run = await client.chat.start(agent_id=agent.id, message="What is a Python SDK?")
            pretty.answer(await run.text())

            # A new version becomes the default. Versions are tagged to the second.
            revised = SKILL_MD.replace("single haiku", "single, vivid haiku")
            (folder / "SKILL.md").write_text(revised)
            skill = await client.skills.upload_version(skill.id, folder)
            pretty.console.print(f"  [bold]version[/]  updated_at={skill.updated_at.isoformat()}")
        finally:
            if agent is not None:
                await client.agents.delete(agent.id)
            await client.skills.delete(skill.id)
            pretty.console.print("  [bold]cleanup[/]  [green]done[/]")


if __name__ == "__main__":
    asyncio.run(main())
