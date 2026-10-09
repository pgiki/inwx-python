"""Contact handle management (``contact.*``): create, info, update, list, delete."""

from __future__ import annotations

from typing import Any

from ..models import Contact
from .base import BaseAPI


def _contact_payload(contact: Contact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(contact, Contact):
        return contact.api_fields()
    data = {k: v for k, v in dict(contact or {}).items() if v not in ("", None)}
    # ``contact.create`` rejects payloads without ``type`` (2003 MISSING_TYPE);
    # default like the ``Contact`` model so dict callers never hit that.
    data["type"] = str(data.get("type") or "PERSON").strip().upper() or "PERSON"
    return data


class ContactsAPI(BaseAPI):
    """Contact save/read (IDs used by domain operations)."""

    def save(self, contact: Contact | dict[str, Any]) -> int:
        """Create a contact handle; returns the numeric id."""
        data = self.call("contact.create", _contact_payload(contact))
        payload = data if isinstance(data, dict) else {}
        return int(payload.get("id") or payload.get("roId") or 0)

    def read(self, contact_id: int) -> Contact:
        """Read a contact handle by id."""
        data = self.call("contact.info", {"id": int(contact_id)})
        payload = data if isinstance(data, dict) else {}
        row = payload.get("contact") if isinstance(payload.get("contact"), dict) else payload
        contact = Contact.from_api(row if isinstance(row, dict) else {})
        if contact.id is None:
            contact.id = int(contact_id)
        return contact

    def update(self, contact_id: int, contact: Contact | dict[str, Any]) -> None:
        """Replace the fields of a contact handle."""
        self.call("contact.update", {"id": int(contact_id), **_contact_payload(contact)})

    def delete(self, contact_id: int) -> None:
        """Delete a contact handle (fails when still attached to a domain)."""
        self.call("contact.delete", {"id": int(contact_id)})

    def list(self, *, search: str | None = None, page: int = 1, page_size: int = 20) -> list[Contact]:
        """List contact handles, optionally filtered by a search string."""
        params: dict[str, Any] = {"page": max(page, 1), "pagelimit": max(1, min(int(page_size), 100))}
        if search:
            params["search"] = search
        data = self.call("contact.list", params)
        payload = data if isinstance(data, dict) else {}
        rows = payload.get("contact") or []
        return [Contact.from_api(r) for r in rows if isinstance(r, dict)]

    def ensure(self, contact: Contact | dict[str, Any] | int) -> int:
        """Return the handle id for ``contact`` (id passthrough, email match, or create).

        A ``Contact``/dict carrying a numeric ``id``/``roId`` is used as-is;
        otherwise the first handle with the same email wins, else a new
        handle is created.
        """
        if isinstance(contact, int):
            return contact
        fields = contact.api_fields() if isinstance(contact, Contact) else dict(contact or {})
        for key in ("id", "roId", "roid"):
            if fields.get(key) not in (None, ""):
                try:
                    return int(fields[key])
                except Exception:
                    pass
        email = str(fields.get("email") or "").strip().lower()
        if email:
            for row in self.list(search=email):
                if row.email.strip().lower() == email:
                    if row.id is not None:
                        return row.id
        return self.save(contact)
