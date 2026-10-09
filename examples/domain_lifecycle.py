"""Domain lifecycle: register/renew/transfer (CHARGED) + info.

⚠️  Spends real money on production. Against OTE (INWX_API_URL override)
everything is free. Dry-run by default; pass --apply and type YES.
Run: INWX_API_URL=https://api.ote.domrobot.com/jsonrpc/ python examples/domain_lifecycle.py --apply test-ote-12345.com
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx  # noqa: E402

CONTACT = {
    "type": "PERSON",
    "name": "Example Testing",
    "street": "4 Example Street",
    "city": "Lagos",
    "pc": "110001",
    "cc": "NG",
    "voice": "+234.8000000000",
    "email": "owner@example.com",
}
NAMESERVERS = ["ns.inwx.de", "ns2.inwx.de", "ns3.inwx.eu"]


def main() -> None:
    apply = "--apply" in sys.argv
    domains = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not domains:
        print("Usage: python examples/domain_lifecycle.py [--apply] <domain>")
        raise SystemExit(2)
    domain = domains[0]
    iw = Inwx()
    print("sandbox:", iw.config.sandbox)

    if not apply:
        print("Dry-run: availability only. Pass --apply and confirm to register.")
        (row,) = iw.domains.check(domain)
        print(f"{row.domain}: {'available' if row.available else 'unavailable'}")
        return
    confirm = input(f"Type YES to REGISTER {domain} (charged on production): ")
    if confirm.strip() != "YES":
        print("Aborted.")
        return
    registered = iw.domains.register(domain, contact=CONTACT, years=1, nameservers=NAMESERVERS)
    print(f"registered: {registered.name} status={registered.status or '-'}")


if __name__ == "__main__":
    main()
