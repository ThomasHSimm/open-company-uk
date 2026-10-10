"""Compare an accounts WIDE extension with its baseline."""

from __future__ import annotations

import argparse
import json

from ukcompany.accounts.extension_audit import compare_wide_extension


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--mode", required=True, choices=("as_first_reported", "latest"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--memory-gb", type=int, default=12)
    args = parser.parse_args()
    report = compare_wide_extension(
        args.baseline,
        args.candidate,
        mode=args.mode,
        output_path=args.output,
        memory_limit_gb=args.memory_gb,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
