# sagupalgu_integrated_base/app/builders/builder_registry.py

from app.builders.joongna_builder import JoongnaPackageBuilder
from app.builders.bunjang_builder import BunjangPackageBuilder
from app.builders.daangn_builder import DaangnPackageBuilder


BUILDER_REGISTRY = {
    "joongna": JoongnaPackageBuilder,
    "bunjang": BunjangPackageBuilder,
    "daangn": DaangnPackageBuilder,
}


def get_builder(platform: str):
    builder_cls = BUILDER_REGISTRY.get(platform)

    if builder_cls is None:
        supported = ", ".join(BUILDER_REGISTRY.keys())
        raise ValueError(
            f"Unsupported platform: {platform}. Supported: {supported}"
        )

    return builder_cls()