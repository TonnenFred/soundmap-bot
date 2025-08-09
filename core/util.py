"""Utility functions for the Soundmap Discord bot.

This module provides helper functions such as chunking iterables into
convenient sized batches for paginating long lists in Discord embeds.
"""

from typing import Iterable, Iterator, TypeVar

T = TypeVar("T")


def chunked(sequence: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield successive chunks of a given size from the input sequence.

    Example:

        >>> list(chunked([1, 2, 3, 4, 5], 2))
        [[1, 2], [3, 4], [5]]

    Args:
        sequence: The iterable to partition.
        size: Maximum length of each chunk. Must be positive.
    Yields:
        Lists of up to ``size`` elements from ``sequence``.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    chunk: list[T] = []
    for item in sequence:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
