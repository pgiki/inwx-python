"""TLD price catalog. Run: python examples/pricing.py com de ai"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx  # noqa: E402


def main() -> None:
    tlds = [a for a in sys.argv[1:] if not a.startswith("--")] or ["com", "de", "ai", "ng"]
    iw = Inwx()
    for row in iw.pricing.catalog(*tlds):
        print(f".{row.tld}: reg={row.register} renew={row.renew} transfer={row.transfer} {row.currency}")


if __name__ == "__main__":
    main()
