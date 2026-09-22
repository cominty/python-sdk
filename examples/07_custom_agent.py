"""Call a custom managed agent created on the platform.

    export COMINTY_CUSTOM_AGENT_ID="<your custom agent id>"
    python examples/07_custom_agent.py

A custom agent is one you configure at platform.cominty.ai -> Agents: its own
model + failover order + custom instructions. From the SDK it's just another
``agent_id``: nothing special to call.

This showcases an agent instructed to turn dense engineering input into a clean,
non-technical **French** briefing for a C-level decision-maker. We feed it a
jargon-heavy incident report (English) and print the executive summary it returns.
"""

from __future__ import annotations

import asyncio

import _pretty as pretty
from _shared import CUSTOM_AGENT_ID, make_client

# Deliberately dense and technical: the agent's job is to make this legible to
# a non-technical executive, in French.
TECHNICAL_INPUT = """\
Incident RCA (recommendations service): p99 inference latency spiked from ~80ms
to ~1.4s for 40 minutes. Root cause: a botched rolling deploy left two Qdrant
shards with mismatched HNSW ef_search params, forcing brute-force vector search.
A gRPC connection-pool memory leak then triggered repeated OOMKilled pods and
CrashLoopBackOff; the HPA scaled replicas 6 -> 22, saturating the node pool and
evicting the Redis embedding-cache sidecar, so cache hit rate collapsed from 94%
to 11%. Mitigation: pinned index params, rolled back the deploy, raised pod
memory limits, added a readiness-probe gate. Follow-ups: canary analysis,
backpressure on the embedding queue, and an SLO alert at p99 > 250ms.\
"""


async def main() -> None:
    if not CUSTOM_AGENT_ID:
        print(
            "Set COMINTY_CUSTOM_AGENT_ID to your custom agent id "
            "(platform.cominty.ai -> Agents) and re-run."
        )
        return

    async with make_client() as client:
        pretty.panel(TECHNICAL_INPUT, title="Technical input (engineering, EN)",
                     style="yellow")

        run = await client.chat.start(
            agent_id=CUSTOM_AGENT_ID,
            message=TECHNICAL_INPUT,
            # Pure transformation: no tools needed, so turn them off for speed
            # and determinism.
            disabled_tools=["web", "company_documents", "mcp:*"],
        )

        async for event in run:
            pretty.render(event)

        # The agent is instructed to reply in French, C-level, bullet points.
        pretty.answer(await run.text(), title="Réponse dirigeant (FR)")


if __name__ == "__main__":
    asyncio.run(main())
