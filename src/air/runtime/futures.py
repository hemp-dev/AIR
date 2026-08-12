"""Small completed-future value used by the sequential AIR scheduler."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FutureValue:
    """A deterministic future handle whose work is completed by ``spawn``.

    The runtime intentionally executes the mock call synchronously in v0.1.
    Keeping a future wrapper at the semantic boundary still lets programs use
    ``agent.spawn``/``agent.await``/``agent.join`` without coupling AIR to an
    asyncio or provider-specific scheduler.
    """

    future_id: str
    target: str
    result: object

    def __post_init__(self) -> None:
        if not self.future_id or not self.target:
            raise ValueError("future_id and target must not be empty")
