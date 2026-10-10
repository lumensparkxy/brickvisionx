"""Materialize a labelled PDF-assisted reference candidate. No automatic inference."""

import json
import sys
from _paths import ROOT
from guide2build.reconstruction.reference import materialize

if __name__ == "__main__":
    result = materialize(ROOT)
    if "--render" in sys.argv:
        from guide2build.reconstruction.evidence import evidence_renders

        evidence_renders(ROOT)
    print(json.dumps({k: v for k, v in result.items() if k not in ("observations", "corrections")}, indent=2))
