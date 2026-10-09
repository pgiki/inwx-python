"""Contact create/read/ensure. Run: python examples/contacts.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Contact, Inwx  # noqa: E402


def main() -> None:
    iw = Inwx()
    handle = iw.contacts.ensure(
        Contact.from_profile(
            name="Example Testing",
            email="owner@example.com",
            street="4 Example Street",
            city="Lagos",
            postcode="110001",
            country="NG",
            phone="+234.8000000000",
        )
    )
    print("handle id:", handle)
    print(iw.contacts.read(handle))


if __name__ == "__main__":
    main()
