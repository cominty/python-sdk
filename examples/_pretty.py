"""Pretty terminal rendering for the examples, built on `rich`.

Run the examples with the dev extras installed (which include `rich`):

    uv sync --all-extras --dev
    python examples/01_stream_events.py

Design:
- **One row per event**, in aligned columns: ``icon  type  detail  meta``.
- **Color means status, everywhere**: running = blue, success = green,
  error = red. The *icon* carries the event type; the model name is dim cyan.
- Long LLM reasoning is shown as a single truncated line, with an explicit dim
  "reasoning hidden" marker so you know there was more.
"""

from __future__ import annotations

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
except ModuleNotFoundError as exc:  # pragma: no cover - example-only guard
    raise SystemExit(
        "examples need 'rich': run `uv sync --all-extras --dev` "
        "(or `pip install rich`)."
    ) from exc

from cominty_sdk import ThreadSummary, events

console = Console()

# Color = status. The same hue always means the same thing.
_STATUS_STYLE = {"running": "blue", "success": "green", "error": "bold red"}
_LABEL_W = 7
_DETAIL_W = 44  # keeps icon+label+detail+meta on one ~80-col line


def _status_style(status: str) -> str:
    return _STATUS_STYLE.get(status, "dim")


def _truncate(text: str, width: int) -> str:
    text = " ".join(text.split())  # collapse newlines/runs of whitespace
    return text if len(text) <= width else text[: width - 1] + "…"


def header(thread_id: object, message_id: object) -> None:
    """Print the thread / message ids that the run is bound to."""
    line = Text("  ")
    line.append("thread ", style="dim")
    line.append(_short(thread_id))
    line.append("  ·  ", style="dim")
    line.append("message ", style="dim")
    line.append(_short(message_id))
    console.print()
    console.print(line)
    console.print()


def render(event: events.AnyEvent) -> None:
    """Render one streamed event as a single aligned row."""
    icon, label, detail, meta, meta_style = _describe(event)

    line = Text("  ")
    line.append(f"{icon} ")
    line.append(f"{label:<{_LABEL_W}}", style="bold")
    line.append("  ")
    line.append(f"{_truncate(detail, _DETAIL_W):<{_DETAIL_W}}")
    if meta:
        line.append("  ")
        line.append(meta, style=meta_style)
    # One row per event: never wrap; crop with … on a too-narrow terminal.
    console.print(line, no_wrap=True, crop=True)

    # LLM reasoning can be a long dump; we showed one truncated line above: flag
    # that the rest is hidden so the stream stays scannable.
    if isinstance(event, events.LlmStep):
        full = " ".join(event.data.description.split())
        if len(full) > _DETAIL_W:
            console.print(
                Text(f"       ↳ reasoning hidden ({len(full)} chars)", style="dim")
            )


def panel(text: str, *, title: str, style: str = "cyan") -> None:
    """Print arbitrary text in a bordered, titled panel."""
    console.print()
    console.print(Panel(text.strip(), title=title, border_style=style,
                        padding=(1, 2)))


def answer(text: str, *, title: str = "Answer") -> None:
    """Print the final assistant reply in a bordered panel."""
    panel(text, title=title, style="green")


def rule(title: str = "") -> None:
    console.print(Rule(title, style="dim"))


def thread_table(threads: list[ThreadSummary], *, title: str) -> None:
    """Render a list of thread summaries as a table."""
    table = Table(title=title, title_justify="left", header_style="bold",
                  expand=False)
    table.add_column("created", style="dim", no_wrap=True)
    table.add_column("★", justify="center", no_wrap=True)
    table.add_column("name")
    table.add_column("id", style="dim", no_wrap=True)
    for t in threads:
        table.add_row(
            f"{t.created_at:%Y-%m-%d}",
            "[yellow]★[/]" if t.starred else "",
            t.name,
            _short(t.id),
        )
    console.print(table)


# --------------------------------------------------------------------------- #
# Per-event formatting: (icon, label, detail, meta, meta_style)
# --------------------------------------------------------------------------- #
def _describe(event: events.AnyEvent) -> tuple[str, str, str, str, str]:
    status_style = _status_style(event.status)

    if isinstance(event, events.ToolCall):
        detail = event.data.error or event.data.message or event.data.name
        return "🔧", "tool", detail, event.status, status_style
    if isinstance(event, events.LlmStep):
        return "🧠", "think", event.data.description, event.data.model, "dim cyan"
    if isinstance(event, events.Result):
        return "💰", "result", f"${event.data.cost.total}", event.status, status_style
    if isinstance(event, events.IntermediaryUpdate):
        return "📝", "update", event.data.message, event.status, status_style
    if isinstance(event, events.UploadingFile):
        return "📤", "upload", event.data.filename, event.status, status_style
    if isinstance(event, (events.WaitingForStart, events.SettingUpSandbox)):
        return "⚙", "setup", event.name, event.status, status_style
    return "•", "event", event.name, event.status, status_style


def _short(value: object) -> str:
    s = str(value)
    return f"{s[:8]}…{s[-4:]}" if len(s) > 14 else s
