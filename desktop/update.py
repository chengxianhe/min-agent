"""Replace this locally built card only; keep the old app for rollback."""

import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--expected-sha256", required=True)
parser.add_argument("--pid", type=int, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = root / "build/AgentProgressCard.app"
target = Path.home() / "Applications/AgentProgressCard.app"
executable = target / "Contents/MacOS/AgentProgressCard"
if hashlib.sha256(executable.read_bytes()).hexdigest() != args.expected_sha256:
    raise SystemExit("已安装版本已变化，拒绝覆盖")
process = subprocess.check_output(["/bin/ps", "-p", str(args.pid), "-o", "comm="], text=True).strip()
if process != str(executable):
    raise SystemExit("进程与本轮卡片不匹配，拒绝停止")
subprocess.run(["codesign", "--verify", "--strict", str(source)], check=True)
token = uuid.uuid4().hex[:8]
staged = target.with_name(f"AgentProgressCard-staged-{token}.app")
backup = target.with_name(f"AgentProgressCard-backup-{token}.app")
shutil.copytree(source, staged)
subprocess.run(["codesign", "--verify", "--strict", str(staged)], check=True)
os.kill(args.pid, signal.SIGTERM)
for _ in range(30):
    try:
        os.kill(args.pid, 0)
    except ProcessLookupError:
        break
    time.sleep(0.1)
else:
    raise SystemExit(f"进程尚未退出；未替换，已准备的版本保留于 {staged}")
target.rename(backup)
try:
    staged.rename(target)
except OSError:
    backup.rename(target)
    raise
print(f"Updated: {target}\nRollback: {backup}")
