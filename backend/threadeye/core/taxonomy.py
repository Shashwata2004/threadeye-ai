"""Defect taxonomy: canonical class ids, labels (en/bn), and simulator/provider aliases."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Literal

import yaml

ClassKind = Literal["defect", "nondefect"]
OTHER_DEFECT = "other_defect"


@dataclass(frozen=True)
class DefectClass:
    id: str
    kind: ClassKind
    label_en: str
    label_bn: str
    is_hole: bool = False
    continuous_default: bool = False


@dataclass(frozen=True)
class Taxonomy:
    version: str
    classes: Mapping[str, DefectClass]
    aliases: Mapping[str, str]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Taxonomy:
        classes: dict[str, DefectClass] = {}
        for kind_key, kind in (("defects", "defect"), ("nondefects", "nondefect")):
            for item in data.get(kind_key, []):
                dc = DefectClass(
                    id=item["id"],
                    kind=kind,  # type: ignore[arg-type]
                    label_en=item["en"],
                    label_bn=item["bn"],
                    is_hole=bool(item.get("is_hole", False)),
                    continuous_default=bool(item.get("continuous_default", False)),
                )
                if dc.id in classes:
                    raise ValueError(f"duplicate class id {dc.id!r}")
                classes[dc.id] = dc
        if OTHER_DEFECT not in classes:
            raise ValueError(f"taxonomy must define {OTHER_DEFECT!r}")
        aliases: dict[str, str] = {}
        for alias, target in (data.get("aliases") or {}).items():
            if target not in classes:
                raise ValueError(f"alias {alias!r} points to unknown class {target!r}")
            aliases[_norm(alias)] = target
        return cls(version=str(data.get("version", "0")), classes=classes, aliases=aliases)

    def resolve(self, name: str) -> str:
        """Map a simulator/provider class name to a canonical id (unknown → ``other_defect``)."""
        key = _norm(name)
        if key in self.classes:
            return key
        return self.aliases.get(key, OTHER_DEFECT)

    def is_known(self, name: str) -> bool:
        key = _norm(name)
        return key in self.classes or key in self.aliases

    def is_nondefect(self, class_id: str) -> bool:
        dc = self.classes.get(class_id)
        return dc is not None and dc.kind == "nondefect"


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


@lru_cache
def load_default_taxonomy() -> Taxonomy:
    text = resources.files("threadeye.data").joinpath("taxonomy.yaml").read_text(encoding="utf-8")
    return Taxonomy.from_mapping(yaml.safe_load(text))
