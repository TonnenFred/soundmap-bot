from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.util import chunked


def test_chunked_splits_sequence_into_expected_sublists():
    sequence = [1, 2, 3, 4, 5]
    result = list(chunked(sequence, 2))
    assert result == [[1, 2], [3, 4], [5]]


@pytest.mark.parametrize("size", [0, -1])
def test_chunked_raises_value_error_for_non_positive_size(size):
    with pytest.raises(ValueError):
        list(chunked([1, 2, 3], size))
