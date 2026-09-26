"""test_offline.py — offline backbone budget + script checks (stdlib + pytest)."""
import os
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# Pinned approximate sizes in GB (conservative planning figures).
SIZES = {
    "wikipedia_en_nopic": 55,
    "stackoverflow": 18,
    "serverfault": 2,
    "superuser": 3,
    "arxiv_cap": 300,
    "cc_slice_working": 100,
}
BUDGET_GB = 1200  # 1.2TB


def test_budget_under_1_2tb():
    total = sum(SIZES.values())
    assert total < BUDGET_GB, f"pinned total {total}GB >= {BUDGET_GB}GB"


def test_scripts_exist_and_executable():
    for name in ("zim.sh", "cc_slice.py", "arxiv_cap.py"):
        p = os.path.join(HERE, name)
        assert os.path.isfile(p), f"missing {name}"
        mode = os.stat(p).st_mode
        assert mode & stat.S_IXUSR, f"{name} missing owner executable bit"


def test_arxiv_cap_refuses_over_400():
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "arxiv_cap.py"),
         "--cats", "cs.AI", "--cap-gb", "401"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "400" in (r.stderr + r.stdout)


def test_arxiv_cap_default_ok():
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "arxiv_cap.py"),
         "--cats", "cs.AI,cs.LG"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "aws s3 sync" in r.stdout


def test_cc_slice_prints_only():
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "cc_slice.py"),
         "--crawl", "CC-MAIN-2026-34", "--domain", "example.com",
         "--out", "/tmp/slice"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "read_parquet" in r.stdout
    assert "aws s3 cp" in r.stdout
    assert "BYTE-RANGE" in r.stdout
