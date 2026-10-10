"""Backend-only local configuration; exported values remain authoritative."""
from pathlib import Path


def load_local_environment(root: Path | None = None) -> None:
    from dotenv import load_dotenv

    repository = root or Path(__file__).resolve().parents[5]
    load_dotenv(repository / ".env", override=False)
