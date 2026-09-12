"""Install the real frontend and onboarding dependencies pinned by HA itself."""

import json
from pathlib import Path
import subprocess
import sys

import homeassistant

root = Path(homeassistant.__file__).parent
pending = ["frontend", "config", "onboarding", "analytics", "cloud", "stream", "hassio", "camera",
           "infrared", "radio_frequency", "ffmpeg", "tts", "conversation", "assist_pipeline"]
seen = set()
requirements = set()
while pending:
    domain = pending.pop()
    if domain in seen:
        continue
    seen.add(domain)
    manifest = json.loads((root / "components" / domain / "manifest.json").read_text())
    requirements.update(manifest.get("requirements", []))
    pending.extend(manifest.get("dependencies", []))
subprocess.run([sys.executable, "-m", "pip", "install", "-c", str(root / "package_constraints.txt"), *sorted(requirements)], check=True)
