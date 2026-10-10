import json
from pathlib import Path
import pytest

@pytest.fixture
def scene_data():
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "tests/fixtures/synthetic.scene.json").read_text())
