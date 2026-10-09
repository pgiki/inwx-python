"""Error shapes and unsupported endpoints (offline). Run: python examples/error_handling.py"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from inwx import Inwx, InwxError, NotSupportedError  # noqa: E402


def main() -> None:
    err = InwxError.from_response({"code": 2303, "msg": "Object does not exist"})
    print("parsed:", err, "| auth_failure:", err.auth_failure)
    iw = Inwx(username="u", password="p")
    try:
        iw.domains.suggest("example.com")
    except NotSupportedError as e:
        print("unsupported:", e)


if __name__ == "__main__":
    main()
