"""Native/packed camera coordinate checks for offline diagnosis."""

import sys
from pathlib import Path

import numpy as np


def test_diagnostic_projection_restores_packed_offsets_and_scale():
    sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
    from diagnose_linescan import overlaps, project

    p = np.array([[50, 310, 6, 100, 0.8, 0.9, 0.1]], np.float32)
    boxes, decoded = project(p, [(0, 0), (500, 0)], 1, 248, 2)
    assert np.allclose(boxes[0], [273.5, -10, 276.5, 40]) is False  # clipped at strip boundary
    assert np.allclose(boxes[0], [273.5, 0, 276.5, 40])
    assert overlaps(boxes, (273, 0, 277, 50))[0]
    assert decoded.shape == (1, 7)
