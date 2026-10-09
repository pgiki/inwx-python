"""Bulk availability checks. Run: python examples/check_availability.py example.com shop.de"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx  # noqa: E402


def main() -> None:
    domains = sys.argv[1:] or ["example.com", "example.de", "myshop.ai"]
    iw = Inwx()
    for row in iw.domains.check(*domains):
        flag = "AVAILABLE" if row.available else "taken"
        premium = " (premium)" if row.premium else ""
        price = f" @{row.price} {row.currency}" if row.price else ""
        print(f"{row.domain}: {flag}{premium}{price}")


if __name__ == "__main__":
    main()
