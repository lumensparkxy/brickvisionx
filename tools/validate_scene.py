import argparse
import json
from pathlib import Path
from _paths import ROOT  # noqa: F401 -- makes the local package importable
from guide2build.core.models import SceneManifest
from guide2build.core.bom import bill_of_materials
from guide2build.releases.models import SceneV2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scene", type=Path)
    args = parser.parse_args()
    data = json.loads(args.scene.read_text())
    model = SceneV2 if data.get("schema_version") == "2.0" else SceneManifest
    scene = model.model_validate(data)
    print(json.dumps({"structural_validation": "pass", "revision": scene.revision,
                      "physical_instances": len(scene.instances), "instruction_snapshots": len(scene.steps),
                      "main_steps": len({(getattr(x, "section_id", "main"), x.main_step_number)
                                         for x in scene.steps if x.main_step_number is not None}),
                      "bom": bill_of_materials(scene),
                      "geometry_check": scene.geometry_check, "connector_check": scene.connector_check,
                      "physical_build_check": scene.physical_build_check}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
