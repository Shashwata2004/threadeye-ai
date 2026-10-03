"""The FrameSource / DetectorProvider contracts and the provider registry (PLAN.md §6.2)."""

import pytest

from threadeye.core.frames import Calibration, FramePacket, FramePosition, FrameSource
from threadeye.core.providers import Detection, ProviderNotConfigured
from threadeye.core.taxonomy import OTHER_DEFECT, Taxonomy, load_default_taxonomy
from threadeye.providers.registry import REGISTRY, create_provider
from threadeye.providers.simulated import PERFECT, REALISTIC


def pos(frame: int = 0) -> FramePosition:
    return FramePosition(frame, 0.0, 0.0, 0.0, 1.1, 18.0, "running", 210.0, False)


def test_detection_validation() -> None:
    ok = Detection((1, 2, 3, 4), "hole", None, "simulated: answer-key defect D1")
    assert ok.confidence is None
    with pytest.raises(ValueError, match="degenerate"):
        Detection((5, 2, 3, 4), "hole", None, "x")
    with pytest.raises(ValueError, match="confidence"):
        Detection((1, 2, 3, 4), "hole", 1.5, "x")
    with pytest.raises(ValueError, match="explanation"):
        Detection((1, 2, 3, 4), "hole", None, "  ")


def test_calibration_validation() -> None:
    c = Calibration(px_per_cm=10, view_region=(0, 0, 1920, 1008), fabric_width_cm=150)
    assert c.view_height_px == 1008
    with pytest.raises(ValueError):
        Calibration(px_per_cm=0, view_region=(0, 0, 1920, 1008), fabric_width_cm=150)


def test_frame_source_is_abstract() -> None:
    with pytest.raises(TypeError):
        FrameSource()  # type: ignore[abstract]


def test_simulated_provider_is_labelled_and_honest() -> None:
    p = create_provider("simulated", {"miss_rate": 0.2})
    info = p.info
    assert info.is_simulated is True
    assert info.kind == "simulated"
    assert info.calibrated_confidence is False  # never invent confidences
    assert "not AI" in info.display_name
    assert info.label.startswith("simulated@")
    assert p.config["miss_rate"] == 0.2 and p.config["jitter_px"] == 0.0
    with pytest.raises(NotImplementedError):  # M1
        p.detect(FramePacket(pos()))


def test_presets() -> None:
    assert all(PERFECT[k] == 0.0 for k in ("miss_rate", "jitter_px", "confusion_rate", "nuisance_flag_rate"))
    assert REALISTIC["miss_rate"] > 0 and REALISTIC["seed"] == 42


@pytest.mark.parametrize("provider_id", ["api", "local_model"])
def test_stubs_are_not_simulated_and_refuse_to_run(provider_id: str) -> None:
    p = create_provider(provider_id)
    assert p.info.is_simulated is False
    with pytest.raises(ProviderNotConfigured):
        p.detect(FramePacket(pos()))


def test_registry() -> None:
    assert set(REGISTRY) == {"simulated", "local_model", "api"}
    with pytest.raises(ValueError, match="unknown provider"):
        create_provider("magic")


def test_taxonomy_default() -> None:
    t = load_default_taxonomy()
    assert t.resolve("Broken End") == "broken_yarn"
    assert t.resolve("hole") == "hole"
    assert t.resolve("never-heard-of-it") == OTHER_DEFECT
    assert t.classes["hole"].is_hole
    assert t.classes["shade_bar"].continuous_default
    assert t.is_nondefect("sticker") and not t.is_nondefect("stain")
    assert all(c.label_bn.strip() and c.label_en.strip() for c in t.classes.values())
    assert {"sticker", "loose_thread", "wrinkle", "pin_hole", "hand", "board"} <= {
        c.id for c in t.classes.values() if c.kind == "nondefect"
    }


def test_taxonomy_rejects_bad_files() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Taxonomy.from_mapping({"defects": [{"id": "x", "en": "x", "bn": "x"}, {"id": "x", "en": "y", "bn": "y"}]})
    with pytest.raises(ValueError, match="other_defect"):
        Taxonomy.from_mapping({"defects": [{"id": "x", "en": "x", "bn": "x"}]})
