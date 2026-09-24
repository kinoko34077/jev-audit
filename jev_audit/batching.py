from __future__ import annotations

from .models import Batch, FileSnapshot


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
        cost = item.chars + len(item.change) + len(item.path) + 32
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
