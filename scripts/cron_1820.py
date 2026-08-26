#!/usr/bin/env python3
"""Hermes no-agent cron entry point for the 18:20 Bible Short."""
from pathlib import Path
import os
import subprocess

ROOT = Path("/Users/clintonemok/Personal/Mum/Youtube/daily-bible-verses-remotion")
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT / "src")
command = [
    "/Users/clintonemok/miniconda3/envs/bible-shorts/bin/python",
    "scripts/run_production.py",
    "--slot", "18:20",
    "--upload",
    "--privacy", "public",
]
result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True)
print(result.stdout)
if result.returncode:
    print(result.stderr)
raise SystemExit(result.returncode)
