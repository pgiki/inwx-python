"""Availability check (free). Run: python examples/quickstart.py example.com"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx  # noqa: E402


def main() -> None:
    domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"
    iw = Inwx()
    (row,) = iw.domains.check(domain)
    extra = f" price={row.price} {row.currency}".rstrip() if row.price else ""
    print(f"{row.domain}: {'available' if row.available else 'unavailable'}{extra}")


if __name__ == "__main__":
    main()
