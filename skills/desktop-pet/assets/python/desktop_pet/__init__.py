"""A pixel pet that lives on an app's windows. The core has no dependencies; each toolkit
has its own adapter module (qt, tk, gtk), imported only by the app that uses it."""

from .core import ACT_PACKS, CAT, CLAWD, GNSS_ACTS, SKINS, Bounds, Ledge, Mood, Mulberry32, Pet, frame, skin_named

__all__ = [
    "ACT_PACKS", "CAT", "CLAWD", "GNSS_ACTS", "SKINS", "Bounds", "Ledge", "Mood", "Mulberry32", "Pet", "frame",
    "skin_named",
]
