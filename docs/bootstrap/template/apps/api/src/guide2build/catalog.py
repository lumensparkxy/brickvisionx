"""Curated source registry: there is no claim of a universal LEGO API."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def find_set(set_number: str) -> dict:
    if not re.fullmatch(r"[0-9]{4,7}", set_number):
        raise ValueError("Set number must contain 4 to 7 digits")
    catalogue = json.loads((ROOT / "config/sets.json").read_text())
    for item in catalogue["sets"]:
        if item["set_number"] == set_number:
            return item
    raise KeyError(set_number)


def find_guide(set_number: str, guide_id: str) -> dict:
    for guide in find_set(set_number)["guides"]:
        if guide["guide_id"] == guide_id:
            return guide
    raise KeyError(guide_id)
