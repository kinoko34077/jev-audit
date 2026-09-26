from __future__ import annotations

from dataclasses import replace

from .models import Batch, FileSnapshot


FILE_BATCH_OVERHEAD_CHARS = 32
CHANGE_TRUNCATION_MARKER = "\n... [jev-audit: change truncated to fit batch] ...\n"


def _truncate_change(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if max_chars <= len(CHANGE_TRUNCATION_MARKER) + 2:
        return text[:max_chars]
    room = max_chars - len(CHANGE_TRUNCATION_MARKER)
    head = max(1, int(room * 0.72))
    tail = max(1, room - head)
    return text[:head] + CHANGE_TRUNCATION_MARKER + text[-tail:]


def fit_files_to_batch_limit(
    files: tuple[FileSnapshot, ...], max_chars: int
) -> tuple[FileSnapshot, ...]:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    fitted: list[FileSnapshot] = []
    for item in files:
        fixed_cost = item.chars + len(item.path) + FILE_BATCH_OVERHEAD_CHARS
        if fixed_cost > max_chars:
            raise ValueError(
                f"file {item.path!r} exceeds max_chars ({fixed_cost} > {max_chars})"
            )
        change_budget = max_chars - fixed_cost
        if len(item.change) > change_budget:
            fitted.append(replace(item, change=_truncate_change(item.change, change_budget)))
        else:
            fitted.append(item)
    return tuple(fitted)


def make_batches(files: tuple[FileSnapshot, ...], max_chars: int) -> tuple[Batch, ...]:
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    result: list[Batch] = []
    current: list[FileSnapshot] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if current:
            result.append(Batch(index=len(result) + 1, files=tuple(current)))
            current = []
            current_chars = 0

    for item in files:
        cost = item.chars + len(item.change) + len(item.path) + FILE_BATCH_OVERHEAD_CHARS
        if cost > max_chars:
            raise ValueError(
                f"file {item.path!r} exceeds max_chars ({cost} > {max_chars})"
            )
        if current and current_chars + cost > max_chars:
            flush()
        current.append(item)
        current_chars += cost
        if current_chars >= max_chars:
            flush()

    flush()
    return tuple(result)
