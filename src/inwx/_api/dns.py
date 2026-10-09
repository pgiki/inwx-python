"""DNS zone + record management (``nameserver.*``)."""

from __future__ import annotations

from typing import Any

from ..idn import to_punycode
from ..models import DNSRecord
from .base import BaseAPI

#: Default INWX nameservers assigned to freshly created zones.
DEFAULT_NAMESERVERS = ["ns.inwx.de", "ns2.inwx.de", "ns3.inwx.eu"]


def _target_fqdn(domain: str, name: str | None) -> str:
    """Normalize a record filter to an FQDN (``@``/bare/relative/FQDN accepted)."""
    z = domain.strip().rstrip(".").lower()
    n = (name or "").strip().rstrip(".")
    if not n or n == "@" or n.lower() == z:
        return z
    if n.lower().endswith("." + z):
        return n.lower()
    return f"{n}.{z}".lower()


class DnsAPI(BaseAPI):
    """DNS hosting on INWX nameservers (MASTER zones + record CRUD)."""

    # -- zones --
    def get_zone(self, domain: str) -> dict[str, Any]:
        """Zone details for ``domain`` (``nameserver.info``)."""
        data = self.call("nameserver.info", {"domain": to_punycode(domain)})
        return data if isinstance(data, dict) else {}

    status = get_zone

    def ensure_zone(
        self, domain: str, *, zone_type: str = "MASTER", nameservers: list[str] | None = None
    ) -> dict[str, Any]:
        """Return the zone, creating it (with INWX default NS) when missing.

        Upstream rejects zone creation without at least two nameservers, so
        ``nameservers`` defaults to :data:`DEFAULT_NAMESERVERS`.
        """
        name = to_punycode(domain)
        try:
            return self.get_zone(name)
        except Exception:
            pass
        hosts = [str(h).strip().rstrip(".") for h in (nameservers or DEFAULT_NAMESERVERS) if str(h or "").strip()]
        self.call("nameserver.create", {"domain": name, "type": zone_type, "ns": hosts})
        return self.get_zone(name)

    provision = ensure_zone

    def delete_zone(self, domain: str) -> None:
        """Delete the whole zone (``nameserver.delete``)."""
        self.call("nameserver.delete", {"domain": to_punycode(domain)})

    def list_zones(self, *, page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """List DNS zones in the account (paginated)."""
        data = self.call(
            "nameserver.list", {"wide": 1, "page": max(page, 1), "pagelimit": max(1, min(int(page_size), 100))}
        )
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("domains") or []
        return [r for r in rows if isinstance(r, dict)]

    # -- records --
    def list(self, domain: str) -> list[DNSRecord]:
        """All records in the zone for ``domain``."""
        zone = self.get_zone(domain)
        rows = zone.get("record") or []
        return [DNSRecord.from_api(r) for r in rows if isinstance(r, dict)]

    def create_record(
        self,
        domain: str,
        name: str,
        record_type: str,
        content: str,
        *,
        ttl: int | None = None,
        priority: int | None = None,
    ) -> DNSRecord:
        """Create one record; returns it re-read from the zone."""
        body: dict[str, Any] = {
            "domain": to_punycode(domain),
            "type": record_type.upper(),
            "name": name or "@",
            "content": content,
        }
        if ttl is not None:
            body["ttl"] = int(ttl)
        if priority is not None:
            body["prio"] = int(priority)
        data = self.call("nameserver.createRecord", body)
        payload = data if isinstance(data, dict) else {}
        record_id = str(payload.get("id") or "")
        for row in self.list(domain):
            if record_id and row.id == record_id:
                return row
        return DNSRecord(type=record_type.upper(), name=name or "@", content=content, ttl=ttl, priority=priority)

    def update_record(self, record_id: str, **fields: Any) -> None:
        """Update record(s) by id (bulk-capable upstream: single id here)."""
        body: dict[str, Any] = {"id": [str(record_id)]}
        for key in ("name", "type", "content", "ttl", "prio", "priority"):
            if fields.get(key) not in (None, ""):
                value = fields[key]
                body["prio" if key == "priority" else key] = value
        self.call("nameserver.updateRecord", body)

    def delete_record(self, record_id: str) -> None:
        """Delete a record by id."""
        self.call("nameserver.deleteRecord", {"id": str(record_id)})

    def delete(self, domain: str, *, record_type: str | None = None, name: str | None = None) -> int:
        """Delete matching records in ``domain``; returns the deletion count."""
        zone = to_punycode(domain)
        target = _target_fqdn(zone, name) if name is not None else None
        doomed = [
            r
            for r in self.list(zone)
            if (record_type is None or r.type.upper() == record_type.upper())
            and (target is None or r.fqdn(zone) == target)
            and r.id
        ]
        for row in doomed:
            assert row.id is not None
            self.delete_record(row.id)
        return len(doomed)

    def set_a_records(self, domain: str, name: str, address: str, *, ttl: int | None = None) -> list[DNSRecord]:
        """Replace all A records for ``name`` with a single ``address``."""
        zone = to_punycode(domain)
        self.ensure_zone(zone)
        target = name.strip().rstrip(".") or "@"
        self.delete(zone, record_type="A", name=target if target == "@" else f"{target}.{zone}")
        created = self.create_record(zone, target, "A", address, ttl=ttl)
        return [created]
