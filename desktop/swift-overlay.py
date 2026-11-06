"""Build-local workaround for duplicate legacy CLT module maps; never edit the SDK."""

import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
info = json.loads(subprocess.check_output(["xcrun", "swiftc", "-print-target-info"]))
include = Path(info["paths"]["runtimeResourcePath"]).parents[1] / "include/swift"
legacy, modern = include / "module.modulemap", include / "bridging.modulemap"
overlay_root = root / "build/swift-overlay"
overlay_root.mkdir(parents=True, exist_ok=True)
roots = []
if legacy.exists() and modern.exists():
    # Only hide the obsolete auto-discovered map when its declarations are identical.
    def declarations(path):
        return re.sub(r"//[^\n]*", "", path.read_text()).strip()
    if declarations(legacy) != declarations(modern):
        raise SystemExit("CLT module maps differ: please repair the toolchain; refusing to mask declarations")
    empty = overlay_root / "empty.modulemap"
    empty.write_text("// Duplicate legacy SwiftBridging declaration omitted for this build only.\n")
    roots.append({"type": "file", "name": str(legacy), "external-contents": str(empty)})
path = overlay_root / "overlay.json"
path.write_text(json.dumps({"version": 0, "roots": roots}))
print(path)
