"""Request-scoped, factual Asante worker progress; never model reasoning."""
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

ProgressSink = Callable[[str, str, list[str]], Awaitable[None]]
progress_sink: ContextVar[ProgressSink | None] = ContextVar("asante_progress_sink", default=None)


async def report_progress(kind: str, message: str, details: list[str] | None = None) -> None:
    sink = progress_sink.get()
    if sink:
        await sink(kind, message, details or [])
