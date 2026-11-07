#!/usr/bin/env python3
"""Runs every *_test.py script in a fresh process (offscreen Qt) and summarises the results."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(here.parent),
           KSNAPMARK_LANG=os.environ.get("KSNAPMARK_LANG", "de"))  # the assertions use the German texts
NEEDS_BUS = {"backend_test.py", "dbus_test.py", "windows_test.py"}  # mock D-Bus services
failed = []
for script in sorted(here.glob("*_test.py")):
    try:
        cmd = [sys.executable, str(script)]
        if script.name in NEEDS_BUS and shutil.which("dbus-run-session"):
            cmd = ["dbus-run-session", "--"] + cmd
        res = subprocess.run(cmd, env=env, cwd=here,
                             capture_output=True, text=True, timeout=300)
        ok = res.returncode == 0
        out_lines = (res.stdout + res.stderr).strip().splitlines()
        tail = out_lines[-1:] or [""]
    except subprocess.TimeoutExpired:
        ok, tail, out_lines = False, ["timeout"], []
    print(f"{'ok  ' if ok else 'FAIL'} {script.name:28} {tail[0][:90]}")
    if not ok:
        failed.append(script.name)
        for extra in out_lines[-25:]:       # full context for the CI log
            print("     | " + extra[:200])
print(f"\n{len(failed)} failed" if failed else "\nall passed")
sys.exit(1 if failed else 0)
