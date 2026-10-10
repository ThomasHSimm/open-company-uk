"""Reconcile accounts features with an aligned register snapshot."""

from __future__ import annotations

import argparse
import json

from ukcompany.accounts.reconciliation import reconcile_accounts_register


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True)
    parser.add_argument("--register", required=True)
    parser.add_argument("--t", required=True, type=int)
    parser.add_argument("--register-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--memory-gb", type=int, default=10)
    parser.add_argument("--spill-dir", default="/tmp/ukcompany-accounts-reconciliation")
    args = parser.parse_args()
    report = reconcile_accounts_register(
        args.features,
        args.register,
        t_yyyymm=args.t,
        register_snapshot_date=args.register_date,
        output_path=args.output,
        memory_limit_gb=args.memory_gb,
        spill_dir=args.spill_dir,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
