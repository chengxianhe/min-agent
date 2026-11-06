"""Install the reviewed local app without overwriting existing apps or preferences."""

import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "build/AgentProgressCard.app"
target = Path.home() / "Applications/AgentProgressCard.app"
subprocess.run(["codesign", "--verify", "--strict", str(source)], check=True)
if target.exists():
    raise SystemExit(f"目标已存在，未覆盖：{target}")
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, target)
subprocess.run(["codesign", "--verify", "--strict", str(target)], check=True)
print(target)
