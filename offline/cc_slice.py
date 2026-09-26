#!/usr/bin/env python3
"""cc_slice.py — Common Crawl slice planner (stdlib only).

SKELETON: prints the DuckDB-over-S3-parquet query and the sample
`aws s3 cp` commands as TEXT. Never executes anything here (no
network, no downloads on this machine).

Byte-range discipline: WARC records are addressed by (warc filename,
offset, length) from the columnar index, fetched with HTTP Range
requests. NEVER `aws s3 cp` a full WARC file.
"""
import argparse


def build_query(crawl: str, domain: str) -> str:
    return (
        f"-- DuckDB over the CC columnar index on S3 (run where network exists):\n"
        f"SELECT warc_filename, warc_record_offset, warc_record_length, url\n"
        f"FROM read_parquet('s3://commoncrawl/cc-index/table/{crawl}/*')\n"
        f"WHERE url_host_registered_domain = '{domain}';"
    )


def build_sample_cp(crawl: str) -> str:
    return (
        f"# Sample 3 wet.paths to inspect the file layout (run where network exists):\n"
        f"aws s3 cp s3://commoncrawl/crawl-data/{crawl}/wet.paths/part-00000.gz - | zcat | head -3"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan a Common Crawl domain slice.")
    ap.add_argument("--crawl", required=True, help="e.g. CC-MAIN-2026-34")
    ap.add_argument("--domain", required=True, help="e.g. example.com")
    ap.add_argument("--out", required=True, help="output dir for the slice manifest")
    args = ap.parse_args()

    print(build_query(args.crawl, args.domain))
    print()
    print(build_sample_cp(args.crawl))
    print()
    print(f"# Slice manifest target: {args.out}/slice.jsonl")
    print("# BYTE-RANGE DISCIPLINE: fetch only (offset,length) ranges via HTTP Range;")
    print("# never full-WARC cp. A full WARC is ~1GB; a slice wants KBs per record.")


if __name__ == "__main__":
    main()
