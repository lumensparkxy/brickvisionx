"""Runtime perception boundary. Never pretend an unavailable provider produced a reconstruction."""
from typing import Protocol


class ProviderUnavailable(RuntimeError):
    pass


class VisionProvider(Protocol):
    def extract_step(self, image_paths: list[str], context: dict) -> dict:
        """Return schema-validated observations; never trusted final assembly coordinates."""
        ...


class DisabledVisionProvider:
    def extract_step(self, image_paths: list[str], context: dict) -> dict:
        raise ProviderUnavailable(
            "No runtime vision provider configured. PDF-assisted authoring is a separate, labelled workflow."
        )
