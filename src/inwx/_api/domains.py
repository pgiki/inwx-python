"""Domain management (``domain.*``): check, create, renew, transfer, update, info, list."""

from __future__ import annotations

from typing import Any

from ..errors import NotSupportedError
from ..idn import to_punycode
from ..models import Contact, Domain, DomainCheck
from .base import BaseAPI
from .contacts import ContactsAPI

#: Period unit appended to year counts (``1`` -> ``"1Y"``).
#: Upstream ``period`` values are TLD-dependent; confirm on OTE if a TLD rejects this.
PERIOD_UNIT = "Y"


def period_param(years: int) -> str:
    """Format a year count as an INWX ``period`` value."""
    return f"{max(1, int(years))}{PERIOD_UNIT}"


def _clean_hosts(hosts: list[str] | None) -> list[str]:
    return [str(h).strip().rstrip(".") for h in (hosts or []) if str(h or "").strip()]


class DomainsAPI(BaseAPI):
    """Domain availability, registration, renewal, transfer and settings."""

    # -- availability --
    def check(self, *domains: str, include_pricing: bool = True) -> list[DomainCheck]:  # noqa: ARG002 - accepted for check-provider compat; INWX always returns premium price
        """Check availability for up to a list of domains in one call.

        Unlike Go54's per-SLD lookup, ``domain.check`` accepts an array of
        full domain names; rows carry ``avail``/``status`` plus premium
        ``price`` when applicable.
        """
        names = [to_punycode(d) for d in domains if (d or "").strip()]
        if not names:
            return []
        data = self.call("domain.check", {"domain": names})
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("domain") or []
        out = [DomainCheck.from_api(str(r.get("domain") or ""), r) for r in rows if isinstance(r, dict)]
        by_domain = {c.domain.strip().lower(): c for c in out}
        ordered = [by_domain[n] for n in names if n in by_domain]
        return ordered or out

    def check_single(self, domain: str) -> DomainCheck:
        """Check a single domain."""
        rows = self.check(domain)
        if not rows:
            raise ValueError(f"No availability result for {domain!r}.")
        return rows[0]

    # -- listing / info --
    def list(self, *, page: int = 1, page_size: int = 20) -> list[Domain]:
        """List owned domains (paginated)."""
        data = self.call(
            "domain.list", {"wide": 1, "page": max(page, 1), "pagelimit": max(1, min(int(page_size), 100))}
        )
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("domain") or []
        return [Domain.model_validate(r) for r in rows if isinstance(r, dict)]

    def get_info(self, domain: str) -> Domain:
        """Detailed info about an owned domain (status, dates, lock, contacts, NS)."""
        data = self.call("domain.info", {"domain": to_punycode(domain)})
        payload = data if isinstance(data, dict) else {}
        return Domain.model_validate(payload or {"domain": domain})

    get = get_info

    def whois(self, domain: str) -> dict[str, Any]:
        """WHMCS-shaped availability equivalent derived from ``check()``."""
        rows = self.check(domain)
        row = rows[0] if rows else None
        return {"status": "available" if row is not None and row.available else "unavailable"}

    # -- contacts helpers --
    def _resolve_contact_ids(self, contact: Contact | dict[str, Any] | dict[str, Any]) -> dict[str, int]:
        """One contact (or role dict) -> ``{registrant, admin, tech, billing}`` id mapping.

        A dict that already holds role ids (or role payloads) is used as-is;
        otherwise a single handle is ensured once and mirrored into all four
        roles (INWX permits shared handles).
        """
        contacts_api = ContactsAPI(self._client)
        if isinstance(contact, dict) and any(contact.get(role) for role in ("registrant", "admin", "tech", "billing")):
            out: dict[str, int] = {}
            for role in ("registrant", "admin", "tech", "billing"):
                value = contact.get(role)
                if isinstance(value, int):
                    out[role] = value
                elif isinstance(value, dict) and value.get("id") not in (None, ""):
                    out[role] = int(value["id"])
                elif value:
                    out[role] = contacts_api.ensure(value)
            fallback = out.get("registrant") or next(iter(out.values()), None)
            if fallback is None:
                raise ValueError("No usable contact ids in role dict.")
            return {role: out.get(role, fallback) for role in ("registrant", "admin", "tech", "billing")}
        handle = contacts_api.ensure(contact)
        return {"registrant": handle, "admin": handle, "tech": handle, "billing": handle}

    # -- registration / renewal / transfer --
    def register(
        self,
        domain: str,
        *,
        contact: Contact | dict[str, Any],
        years: int = 1,
        period: str | None = None,
        nameservers: list[str] | None = None,
        transfer_lock: bool = True,
        renewal_mode: str | None = None,
        whois_protection: bool | None = None,  # noqa: ARG002 - accepted for compat; no per-order flag upstream
        auto_renew: bool | None = None,  # noqa: ARG002 - accepted for compat; use renewal_mode instead
        wait: bool = True,  # noqa: ARG002 - synchronous API; accepted for compat
        timeout: float = 30.0,  # noqa: ARG002 - accepted for compat
        poll_interval: float = 5.0,  # noqa: ARG002 - accepted for compat
    ) -> Domain:
        """Register a domain (charges the account on registry success)."""
        name = to_punycode(domain)
        body: dict[str, Any] = {
            "domain": name,
            "period": period or period_param(years),
            **self._resolve_contact_ids(contact),
        }
        hosts = _clean_hosts(nameservers)
        if hosts:
            body["ns"] = hosts
        body["transferLock"] = 1 if transfer_lock else 0
        if renewal_mode:
            body["renewalMode"] = renewal_mode
        data = self.call("domain.create", body)
        payload = data if isinstance(data, dict) else {}
        if payload.get("roId"):
            return self.get_info(name)
        return Domain.model_validate({"domain": name})

    def renew(
        self,
        domain: str,
        *,
        years: int = 1,
        period: str | None = None,
        current_expiration: str | None = None,
        wait: bool = True,  # noqa: ARG002 - accepted for compat
        timeout: float = 30.0,  # noqa: ARG002 - accepted for compat
        poll_interval: float = 5.0,  # noqa: ARG002 - accepted for compat
    ) -> Domain:
        """Renew an owned domain (``expiration`` auto-fetched when omitted)."""
        name = to_punycode(domain)
        if current_expiration is None:
            info = self.get_info(name)
            if info.expiry_date is not None:
                current_expiration = info.expiry_date.strftime("%Y-%m-%d")
        body: dict[str, Any] = {"domain": name, "period": period or period_param(years)}
        if current_expiration:
            body["expiration"] = current_expiration
        self.call("domain.renew", body)
        return self.get_info(name)

    def transfer(
        self,
        domain: str,
        *,
        contact: Contact | dict[str, Any] | None = None,
        auth_code: str | None = None,
        eppcode: str | None = None,
        years: int = 1,
        period: str | None = None,
        nameservers: list[str] | None = None,
        transfer_lock: bool = True,
        renewal_mode: str | None = None,
        wait: bool = True,  # noqa: ARG002 - accepted for compat
        timeout: float = 30.0,  # noqa: ARG002 - accepted for compat
        poll_interval: float = 5.0,  # noqa: ARG002 - accepted for compat
    ) -> Domain:
        """Submit a domain transfer (charged on registry success)."""
        name = to_punycode(domain)
        body: dict[str, Any] = {"domain": name, "period": period or period_param(years)}
        if contact is not None:
            body.update(self._resolve_contact_ids(contact))
        code = eppcode or auth_code
        if code:
            body["authCode"] = code
        hosts = _clean_hosts(nameservers)
        if hosts:
            body["ns"] = hosts
        body["transferLock"] = 1 if transfer_lock else 0
        if renewal_mode:
            body["renewalMode"] = renewal_mode
        data = self.call("domain.transfer", body)
        payload = data if isinstance(data, dict) else {}
        if payload.get("roId"):
            try:
                return self.get_info(name)
            except Exception:
                pass
        return Domain.model_validate({"domain": name})

    def restore(self, domain: str) -> Domain:
        """Restore a domain from redemption."""
        name = to_punycode(domain)
        self.call("domain.restore", {"domain": name})
        return self.get_info(name)

    def trade(self, domain: str, *, contact: Contact | dict[str, Any]) -> Domain:
        """Change the owner (registrant) of a domain."""
        name = to_punycode(domain)
        handle = ContactsAPI(self._client).ensure(contact)
        self.call("domain.trade", {"domain": name, "registrant": handle})
        return self.get_info(name)

    # -- contacts / nameservers / lock / EPP --
    def get_contacts(self, domain: str) -> dict[str, Any]:
        """Contact IDs attached to a domain."""
        info = self.get_info(domain)
        return {
            "registrant": info.registrant_id,
            "admin": info.admin_id,
            "tech": info.tech_id,
            "billing": info.billing_id,
        }

    def set_contacts(self, domain: str, contacts: dict[str, Any]) -> Domain:
        """Replace the contact IDs attached to a domain (``domain.update``)."""
        name = to_punycode(domain)
        body: dict[str, Any] = {"domain": name}
        for role in ("registrant", "admin", "tech", "billing"):
            value = (contacts or {}).get(role)
            if isinstance(value, dict):
                value = ContactsAPI(self._client).ensure(value)
            if value not in (None, ""):
                body[role] = int(value)
        self.call("domain.update", body)
        return self.get_info(name)

    def get_nameservers(self, domain: str) -> list[str]:
        return self.get_info(domain).nameservers

    def set_nameservers(self, domain: str, hosts: list[str] | None) -> list[str]:
        """Point a domain at custom nameservers (``domain.update`` ``ns``)."""
        name = to_punycode(domain)
        clean = _clean_hosts(hosts)
        self.call("domain.update", {"domain": name, "ns": clean})
        return self.get_nameservers(name)

    def get_lock(self, domain: str) -> bool:
        return self.get_info(domain).locked

    def set_lock(self, domain: str, locked: bool) -> bool:
        name = to_punycode(domain)
        self.call("domain.update", {"domain": name, "transferLock": 1 if locked else 0})
        try:
            return self.get_info(name).locked
        except Exception:
            return locked

    def lock(self, domain: str) -> bool:
        return self.set_lock(domain, True)

    def unlock(self, domain: str) -> bool:
        return self.set_lock(domain, False)

    def get_auth_code(self, domain: str) -> str:
        """EPP auth code for a domain (for transferring it away)."""
        return self.get_info(domain).auth_code

    def set_privacy(self, domain: str, enabled: bool) -> bool:
        """Toggle INWX Whois Privacy (``domain.update`` ``extData``).

        Mirrors the official INWX WHMCS plugin (``inwx_IDProtectToggle``):
        ``extData={"WHOIS-PROTECTION": bool}`` replaces all four contacts
        with the privacy proxy. Only shield-marked TLDs accept it; others
        reject the update (callers treat that as a logged warning, never a
        registration failure).
        """
        name = to_punycode(domain)
        self.call(
            "domain.update",
            {"domain": name, "extData": {"WHOIS-PROTECTION": bool(enabled)}},
        )
        return bool(enabled)

    def set_autorenew(self, domain: str, enabled: bool, mode: str = "AUTORENEW") -> Domain:
        """Set the renewal mode (default ``AUTORENEW``; e.g. ``AUTOEXPIRE`` to disable)."""
        name = to_punycode(domain)
        self.call("domain.update", {"domain": name, "renewalMode": mode if enabled else "AUTOEXPIRE"})
        return self.get_info(name)

    def get_tld_list(self) -> list[str]:
        """All known TLDs via ``domain.getRules`` (no TLD filter)."""
        data = self.call("domain.getRules", {})
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("rules") or []
        return sorted({str(r.get("tld", "")).lstrip(".") for r in rows if isinstance(r, dict) and r.get("tld")})

    def suggest(self, domain: str, **params: Any) -> list:
        raise NotSupportedError(
            f"suggest({domain}) has no INWX endpoint.",
            alternative="Fan check() out over candidate FQDNs instead.",
        )
