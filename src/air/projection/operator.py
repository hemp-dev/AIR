"""Deterministic human/operator projection over structured AIR events."""

from __future__ import annotations

from dataclasses import dataclass

from ..runtime.events import Event


@dataclass(frozen=True, slots=True)
class OperatorMessage:
    """Human-facing summary derived from one or more structured events."""

    level: int
    kind: str
    text: str
    refs: tuple[str, ...] = ()


class OperatorProjection:
    """Rule-based renderer; it never mutates state or events."""

    def render(self, events: tuple[Event, ...] | list[Event]) -> tuple[OperatorMessage, ...]:
        messages: list[OperatorMessage] = []
        committed = False
        for event in events:
            if event.event_type == "task.started":
                messages.append(OperatorMessage(1, "started", "Task started."))
            elif event.event_type == "state.commit":
                committed = True
                messages.append(
                    OperatorMessage(
                        1, "milestone", "Verified result committed to shared state.", event.refs
                    )
                )
            elif event.event_type == "verification.rejected":
                messages.append(
                    OperatorMessage(
                        2,
                        "verification_failed",
                        "Verification failed: "
                        f"{event.json_payload().get('message', 'invalid AIR program')}.",
                        event.refs,
                    )
                )
            elif event.event_type == "state.patch.rejected":
                messages.append(
                    OperatorMessage(
                        2,
                        "write_rejected",
                        "State patch rejected; no mutation was applied.",
                        event.refs,
                    )
                )
            elif event.event_type == "state.conflict":
                messages.append(
                    OperatorMessage(
                        2,
                        "conflict",
                        "State conflict detected; no overwrite was applied.",
                        event.refs,
                    )
                )
            elif event.event_type == "human.required":
                messages.append(
                    OperatorMessage(
                        2, "human_required", "Human authorization is required.", event.refs
                    )
                )
            elif event.event_type == "op.failed":
                payload = event.json_payload()
                messages.append(
                    OperatorMessage(
                        2,
                        "operation_failed",
                        f"Operation failed: {payload.get('message', 'runtime failure')}.",
                        event.refs,
                    )
                )
            elif event.event_type == "task.completed":
                text = (
                    "Task completed successfully; verified result committed to shared state."
                    if committed
                    else "Task completed successfully."
                )
                messages.append(OperatorMessage(1, "completed", text))
            elif event.event_type == "task.failed":
                messages.append(OperatorMessage(2, "failed", "Task failed."))
        return tuple(messages)
