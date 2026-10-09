"""DNS zone + records. Run: python examples/dns_manage.py example.com [--apply]"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx  # noqa: E402


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    domain = args[0] if args else "example.com"
    apply = "--apply" in sys.argv
    iw = Inwx()
    for row in iw.dns.list(domain):
        print(f"{row.type} {row.fqdn(domain)} -> {row.content} (id={row.id})")
    if apply:
        created = iw.dns.create_record(domain, "shop", "A", "5.6.7.8", ttl=300)
        print("created:", created)
    else:
        print("Dry-run: pass --apply to create a sample A record.")


if __name__ == "__main__":
    main()
