"""Explicit check scopes; absent tools never count as successful checks."""
import argparse
import subprocess
import sys
from _paths import ROOT


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-only", action="store_true", help="Only Python tests and schema drift; no UI claim")
    parser.add_argument("--e2e", action="store_true", help="Also run Playwright; no external inference")
    args = parser.parse_args()
    commands = [
        [sys.executable, "-m", "pytest"],
        [sys.executable, "tools/export_schema.py", "--check"],
    ]
    if not args.python_only:
        commands.extend([[sys.executable, "-m", "ruff", "check", "apps/api", "tools", "tests/backend"],
                         ["npm", "run", "check"]])
    if args.e2e:
        commands.append(["npm", "run", "test:e2e"])
    print("CHECK SCOPE:", "python-contracts-only" if args.python_only else "local-software", flush=True)
    for command in commands:
        print("RUN:", " ".join(command), flush=True)
        try:
            result = subprocess.run(command, cwd=ROOT, check=False)
        except FileNotFoundError as error:
            print(f"BLOCKED: {error}")
            return 2
        if result.returncode:
            return result.returncode
    print("Selected checks passed. This does not certify the target model or physical build.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
