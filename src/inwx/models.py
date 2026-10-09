"""Pydantic models for INWX DomRobot API responses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InwxModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True, extra="allow")


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "locked", "available", "active", "success", "ok"}


def _to_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(value).strip()[:19], fmt)
        except Exception:
            continue
    return None


class DomainCheck(InwxModel):
    """Availability result for one domain (``domain.check`` row)."""

    domain: str = ""
    available: bool = False
    premium: bool = False
    price: Decimal | None = None
    currency: str = ""
    reason: str | None = None
    status: str = ""

    @field_validator("price", mode="before")
    @classmethod
    def _parse_price(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @classmethod
    def from_api(cls, domain: str, row: dict[str, Any]) -> DomainCheck:
        """Build from a ``domain.check`` row (``avail``/``status`` spellings)."""
        row = dict(row or {})
        status = str(row.get("status") or "").strip().lower()
        avail = row.get("avail")
        if avail is None:
            available = status in {"available", "free", "ok"}
        else:
            available = avail is True or str(avail).strip() in {"1", "true", "yes"}
        premium_block = row.get("premium")
        price = row.get("price")
        if price in (None, "") and isinstance(premium_block, dict):
            price = premium_block.get("reg") or premium_block.get("register")
        return cls.model_validate(
            {
                "domain": row.get("domain") or domain,
                "available": available,
                "premium": bool(premium_block) or _to_bool(row.get("isPremium")),
                "price": price,
                "currency": row.get("currency") or "",
                "reason": row.get("reason") or None,
                "status": status,
            }
        )

    # -- spaceship-shaped compat --
    @property
    def result(self) -> str:
        return "available" if self.available else "unavailable"


class Domain(InwxModel):
    """An owned domain (``domain.info`` / ``domain.list`` shape)."""

    id: int | None = Field(default=None, alias="roId")
    name: str = Field(default="", alias="domain")
    unicode_name: str = Field(default="", alias="domain-ace")
    status: str = ""
    period: str = ""
    registration_date: datetime | None = Field(default=None, alias="crDate")
    expiry_date: datetime | None = Field(default=None, alias="exDate")
    updated_date: datetime | None = Field(default=None, alias="upDate")
    locked: bool = Field(default=False, alias="transferLock")
    auth_code: str = Field(default="", alias="authCode")
    renewal_mode: str = Field(default="", alias="renewalMode")
    registrant_id: int | None = Field(default=None, alias="registrant")
    admin_id: int | None = Field(default=None, alias="admin")
    tech_id: int | None = Field(default=None, alias="tech")
    billing_id: int | None = Field(default=None, alias="billing")
    nameservers: list[str] = Field(default_factory=list, alias="ns")

    @field_validator("registration_date", "expiry_date", "updated_date", mode="before")
    @classmethod
    def _parse_dt(cls, v: Any) -> datetime | None:
        return _to_datetime(v)

    @field_validator("locked", mode="before")
    @classmethod
    def _parse_locked(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("nameservers", mode="before")
    @classmethod
    def _parse_ns(cls, v: Any) -> list[str]:
        if isinstance(v, dict):
            v = list(v.values())
        if isinstance(v, (list, tuple)):
            return [str(h).strip().rstrip(".") for h in v if str(h or "").strip()]
        return []

    @field_validator("registrant_id", "admin_id", "tech_id", "billing_id", mode="before")
    @classmethod
    def _parse_id(cls, v: Any) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except Exception:
            return None

    # -- spaceship-shaped compat --
    @property
    def expiration_date(self) -> datetime | None:
        return self.expiry_date


class Contact(InwxModel):
    """An INWX contact handle (``contact.create``/``contact.info`` fields)."""

    id: int | None = Field(default=None, alias="roId")
    type: str = "PERSON"
    name: str = ""
    organization: str | None = Field(default=None, alias="org")
    street: str = ""
    city: str = ""
    postal_code: str = Field(default="", alias="pc")
    state: str | None = Field(default=None, alias="sp")
    country: str = Field(default="", alias="cc")
    phone: str = Field(default="", alias="voice")
    fax: str | None = None
    email: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return str(v or "PERSON").strip().upper() or "PERSON"

    def api_fields(self) -> dict[str, Any]:
        """Field payload for ``contact.create``/``contact.update`` (wire keys)."""
        data: dict[str, Any] = {
            "type": self.type or "PERSON",
            "name": self.name,
            "street": self.street,
            "city": self.city,
            "pc": self.postal_code,
            "cc": self.country,
            "voice": self.phone,
            "email": self.email,
        }
        optional = {"org": self.organization, "sp": self.state, "fax": self.fax}
        data.update({k: v for k, v in optional.items() if v not in ("", None)})
        return {k: v for k, v in data.items() if v not in ("", None)}

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Contact:
        """Parse accepting ``id`` or ``roId``."""
        row = dict(data or {})
        if row.get("roId") in (None, "") and row.get("id") not in (None, ""):
            row["roId"] = row.pop("id")
        return cls.model_validate(row)

    @classmethod
    def from_profile(
        cls,
        *,
        name: str = "",
        email: str = "",
        street: str = "",
        city: str = "",
        postcode: str = "",
        state: str = "",
        country: str = "",
        phone: str = "",
        organization: str | None = None,
    ) -> Contact:
        """Build from fikashop profile facts."""
        return cls(
            type="ORG" if (organization or "").strip() else "PERSON",
            name=name.strip(),
            organization=(organization or "").strip() or None,
            street=street.strip(),
            city=city.strip(),
            postal_code=postcode.strip(),
            state=state.strip() or None,
            country=country.strip().upper(),
            phone=phone.strip(),
            email=email.strip(),
        )


class DNSRecord(InwxModel):
    """A DNS resource record (``nameserver.info`` record rows)."""

    id: str | None = None
    type: str = ""
    name: str = "@"
    content: str | None = None
    ttl: int | None = None
    priority: int | None = Field(default=None, alias="prio")

    @field_validator("type", mode="before")
    @classmethod
    def _upper(cls, v: Any) -> Any:
        return str(v).upper() if v else v

    @field_validator("ttl", "priority", mode="before")
    @classmethod
    def _parse_int(cls, v: Any) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except Exception:
            return None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> DNSRecord:
        row = dict(data or {})
        # Accept spaceship-style ``address``/``value`` as aliases for ``content``.
        if row.get("content") in (None, ""):
            for key in ("address", "value"):
                if row.get(key) not in (None, ""):
                    row["content"] = row.pop(key)
                    break
        return cls.model_validate(row)

    # -- spaceship-shaped compat (``address`` instead of ``content``) --
    @property
    def address(self) -> str | None:
        return self.content

    @address.setter
    def address(self, val: str | None) -> None:
        self.content = val

    def fqdn(self, zone: str) -> str:
        """Fully qualified name of this record inside ``zone``."""
        z = zone.strip().rstrip(".").lower()
        n = (self.name or "").strip().rstrip(".")
        if not n or n == "@" or n.lower() == z:
            return z
        if n.lower().endswith("." + z):
            return n.lower()
        return f"{n}.{z}".lower()

    def to_api(self) -> dict[str, Any]:
        """Record payload for create/update (no empties)."""
        data: dict[str, Any] = {"type": self.type.upper(), "name": self.name or "@"}
        if self.content not in (None, ""):
            data["content"] = self.content
        if self.ttl is not None:
            data["ttl"] = self.ttl
        if self.priority is not None:
            data["prio"] = self.priority
        return data


class TldPrice(InwxModel):
    """A ``domain.getPrices`` row for one TLD (per-year prices)."""

    tld: str = ""
    currency: str = ""
    register: Decimal | None = Field(default=None, alias="createPrice")
    renew: Decimal | None = Field(default=None, alias="renewalPrice")
    transfer: Decimal | None = Field(default=None, alias="transferPrice")
    update: Decimal | None = Field(default=None, alias="updatePrice")
    promo: bool = False

    @field_validator("register", "renew", "transfer", "update", mode="before")
    @classmethod
    def _parse_price(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("promo", mode="before")
    @classmethod
    def _parse_promo(cls, v: Any) -> bool:
        return bool(v) if isinstance(v, dict) else _to_bool(v)
