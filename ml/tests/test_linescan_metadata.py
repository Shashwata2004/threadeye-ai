import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from linescan_metadata import normalized_metadata


def test_expected_score_rounding_fix_preserves_geometry_labels_and_source():
    data = {
        "roll_length_yd": 6.561,
        "fabric_width_in": 60.0,
        "source": "frozen",
        "classes": ["broken_yarn"],
        "expected_score": {
            "total_points": 23,
            "points_per_100_sq_yd": 210.30,
            "threshold": 40,
            "verdict": "FAIL",
        },
    }
    payload = json.dumps(data).encode()
    updated, proof = normalized_metadata(payload)
    actual = json.loads(updated)
    assert proof and actual["expected_score"]["points_per_100_sq_yd"] == round(
        23 * 3600 / (6.561 * 60), 2
    )
    assert {k: v for k, v in actual.items() if k != "expected_score"} == {
        k: v for k, v in data.items() if k != "expected_score"
    }
    assert normalized_metadata(updated) == (updated, None)
