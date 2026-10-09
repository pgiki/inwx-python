"""Internationalized domain name helpers (ASCII A-label <-> Unicode)."""

from __future__ import annotations


def to_punycode(domain: str) -> str:
    """Convert a (possibly Unicode) domain to its ASCII A-label form."""
    return (domain or "").strip().rstrip(".").lower().encode("idna").decode("ascii")


def from_punycode(domain: str) -> str:
    """Convert an ASCII A-label domain back to Unicode (best effort)."""
    try:
        return (domain or "").encode("ascii").decode("idna")
    except Exception:
        return domain or ""


def split_domain(domain: str) -> tuple[str, str]:
    """Split ``example.com`` into ``("example", "com")`` (SLD + rest)."""
    name = to_punycode(domain)
    if "." not in name:
        return name, ""
    sld, _, rest = name.partition(".")
    return sld, rest
