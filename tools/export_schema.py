import argparse
import json
from _paths import ROOT
from guide2build.core.models import SceneManifest
from guide2build.releases.models import SceneV2, ReleaseValidation
from guide2build.releases.alpha import AlphaDisclosure, AlphaCoverage, AlphaReleaseValidation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    contracts = [('scene', SceneManifest), ('scene-v2', SceneV2), ('release-validation', ReleaseValidation),
                 ('alpha-disclosure', AlphaDisclosure), ('alpha-coverage', AlphaCoverage),
                 ('alpha-release-validation', AlphaReleaseValidation)]
    for name, contract in contracts:
        target = ROOT / f"packages/contracts/{name}.schema.json"
        schema = contract.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        output = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if args.check:
            if not target.exists() or target.read_text() != output:
                print(f"{name} schema differs; run tools/export_schema.py and review the diff.")
                return 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output)
            print(f"Wrote {target.relative_to(ROOT)}")
    if args.check:
        print("All schemas are current.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
