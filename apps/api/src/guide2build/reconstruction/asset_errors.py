"""Internal resolver failures; provider JSON cannot instantiate this boundary."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RejectedResource:
    root_part_id: str
    resource_path: str
    dependency_chain: tuple[str, ...]
    classification: str
    official_url: str
    resource_sha256: str
    size_bytes: int
    license_notices: tuple[str, ...]
    untraversed_dependency_names: tuple[str, ...]

    def receipt(self):
        return asdict(self)


class UnsupportedIndividualClosure(Exception):
    """Only a fully checked envelope with the known Shortcut classification."""

    def __init__(self, evidence, *, contexts=()):
        self.evidence = tuple(evidence)
        self.contexts = tuple(contexts)
        super().__init__("New individual design uses prohibited Shortcut geometry")
