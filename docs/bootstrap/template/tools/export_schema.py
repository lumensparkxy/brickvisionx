import argparse
import json
from _paths import ROOT
from guide2build.core.models import SceneManifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "packages/contracts/scene.schema.json"
    schema = SceneManifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    output = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not target.exists() or target.read_text() != output:
            print("Schema differs from Python contracts; run tools/export_schema.py and review the diff.")
            return 1
        print("Schema is current.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output)
    print(f"Wrote {target.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
