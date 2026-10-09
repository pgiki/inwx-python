"""TLD price catalog (``domain.getPrices`` / ``domain.getdomainprice``)."""

from __future__ import annotations

from typing import Any

from ..idn import to_punycode
from ..models import TldPrice
from .base import BaseAPI


class PricingAPI(BaseAPI):
    """Register/renew/transfer prices per TLD (no API key beyond login)."""

    def catalog(self, *tlds: str) -> list[TldPrice]:
        """Full (or TLD-filtered) price catalog: one row per TLD."""
        params: dict[str, Any] = {}
        clean = [t.strip().lstrip(".").lower() for t in tlds if (t or "").strip()]
        if clean:
            params["tld"] = clean
        data = self.call("domain.getPrices", params)
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("price") or []
        return [TldPrice.model_validate(r) for r in rows if isinstance(r, dict)]

    def get_price(self, domain: str, pricetype: str = "reg") -> dict[str, Any]:
        """Price for one domain + action (``reg``/``renewal``/``transfer``/...)."""
        data = self.call("domain.getdomainprice", {"domain": [to_punycode(domain)], "pricetype": pricetype})
        return data if isinstance(data, dict) else {}
