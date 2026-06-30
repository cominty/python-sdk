# Examples

Runnable scripts for each common scenario. They render colored, aligned output
with [`rich`](https://github.com/Textualize/rich) (shared helper:
[`_pretty.py`](_pretty.py)), installed via the dev extras:

```bash
uv sync --all-extras --dev      # or: pip install rich
```

They read credentials from the environment, so set these once:

```bash
export COMINTY_API_KEY="<your API key>"     # platform.cominty.ai -> API keys
export COMINTY_USER_ID="user_..."           # platform.cominty.ai -> Profile
# optional:
export COMINTY_AGENT_ID="__cominty_agents::agent.chat"   # else the default is used
export COMINTY_BASE_URL="https://ds-dev.cominty.com"     # else production
```

Then run any script from the repo root:

```bash
python examples/01_stream_events.py
```

| Script | Shows |
|--------|-------|
| [`01_stream_events.py`](01_stream_events.py) | Stream progress events (tool calls, LLM steps, result) live |
| [`02_await_result.py`](02_await_result.py) | Fire a message and just await the final answer |
| [`03_follow_up.py`](03_follow_up.py) | Continue the conversation in the same thread (`chat.send`) |
| [`04_answer_questions.py`](04_answer_questions.py) | Read the agent's clarifying questions and answer them |
| [`05_list_threads.py`](05_list_threads.py) | List and search a user's threads |
| [`06_manage_thread.py`](06_manage_thread.py) | Get, rename/star, and archive a thread |
| [`07_custom_agent.py`](07_custom_agent.py) | Call a custom managed agent (needs `COMINTY_CUSTOM_AGENT_ID`) |
| [`08_mcp_linear.py`](08_mcp_linear.py) | Custom agent pulls live context from the Linear MCP server |

> Shared client setup lives in [`_shared.py`](_shared.py).
