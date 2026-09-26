#!/usr/bin/env python3
"""arxiv_cap.py — arXiv S3 subset planner (stdlib only).

SKELETON: prints `aws s3 sync --include` subset commands as TEXT.
Never executes anything here. Budget: cap_gb must be <= 400.
"""
import argparse

MAX_CAP_GB = 400


def build_sync_cmds(cats: list[str], cap_gb: int) -> str:
    lines = [
        f"# arXiv S3 subset (cap {cap_gb}GB, run where network exists):",
        "# Bucket: s3://arxiv/src/  (filenames encode yymm + category)",
    ]
    for c in cats:
        lines.append(
            f"aws s3 sync s3://arxiv/src/ ./arxiv-src/ "
            f"--exclude '*' --include '*{c}*'"
        )
    return "\n".join(lines)


def check_budget(cap_gb: int) -> None:
    assert cap_gb <= MAX_CAP_GB, f"cap {cap_gb}GB exceeds {MAX_CAP_GB}GB budget"


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan an arXiv S3 subset pull.")
    ap.add_argument("--cats", required=True, help="comma list, e.g. cs.AI,cs.LG,cs.CL")
    ap.add_argument("--cap-gb", type=int, default=300)
    args = ap.parse_args()

    check_budget(args.cap_gb)
    cats = [c.strip() for c in args.cats.split(",") if c.strip()]
    print(build_sync_cmds(cats, args.cap_gb))


if __name__ == "__main__":
    main()
