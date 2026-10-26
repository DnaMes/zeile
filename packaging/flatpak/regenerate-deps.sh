#!/bin/bash
# Regenerate python-deps.json (needs uv, the Flatpak GNOME 50 SDK and flatpak-pip-generator.py
# from https://github.com/flatpak/flatpak-builder-tools/tree/master/pip).
#   packaging/flatpak/regenerate-deps.sh /path/to/flatpak-pip-generator.py
# markdown is part of the GNOME runtime; pygments only of the SDK, so it is installed
# explicitly (--ignore-installed, for that module only) to land in /app. nh3 comes as a pinned platform wheel (Rust build avoided).
set -euo pipefail

readonly GENERATOR="${1:?usage: regenerate-deps.sh /path/to/flatpak-pip-generator.py}"
cd "$(dirname "$0")"

uv run --with requirements-parser --with packaging python "$GENERATOR" \
    --runtime org.gnome.Sdk//50 --output python-deps --prefer-wheels nh3 \
    pygments pymdown-extensions nh3

python3 - <<'PY'
import json
from pathlib import Path

path = Path("python-deps.json")
data = json.loads(path.read_text())
for module in data["modules"]:
    if module["name"] == "python3-pygments":
        module["build-commands"] = [
            c.replace("--exists-action=i", "--exists-action=i --ignore-installed")
            for c in module["build-commands"]
        ]
path.write_text(json.dumps(data, indent=4) + "\n")
PY
