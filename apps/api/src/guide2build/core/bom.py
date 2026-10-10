"""Counts physical instances, never step appearances or subassembly attachment events."""
from collections import Counter
from .models import SceneManifest


def bill_of_materials(scene: SceneManifest) -> list[dict[str, str | int]]:
    counts = Counter((part.part_id, part.color_code) for part in scene.instances)
    return [{"part_id": part, "color_code": color, "quantity": count}
            for (part, color), count in sorted(counts.items())]
