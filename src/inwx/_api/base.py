"""Base JSON-RPC transport for all INWX DomRobot endpoint groups.

Wire format::

    POST {api_url}  {"method": "domain.check", "params": {...}}
    -> {"code": 1000, "msg": "...", "resData": {...}}

Session handling: the first call performs ``account.login`` (cookies persist
on the ``httpx.Client`` jar); a ``2200``-class auth failure triggers one
re-login + retry. ``close()`` on the client calls ``account.logout``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from ..errors import PENDING, SESSION_END, SUCCESS, InwxError
from ..logging import get_logger

if TYPE_CHECKING:
    from ..client import Inwx

logger = get_logger("api")


class BaseAPI:
    """Shared request handling: session login, error mapping, resData unwrap."""

    def __init__(self, client: Inwx) -> None:
        self._client = client

    @property
    def _http(self) -> httpx.Client:
        return self._client._http

    # -- session --
    def login(self) -> dict[str, Any]:
        """Authenticate (``account.login``); returns the login ``resData``."""
        data = self._raw("account.login", {"user": self._client.config.username, "pass": self._client.config.password})
        self._client._logged_in = True
        return data if isinstance(data, dict) else {}

    def logout(self) -> None:
        """End the session (``account.logout``); never raises."""
        try:
            self._raw("account.logout", {})
        except Exception:
            pass
        self._client._logged_in = False

    def ping(self) -> bool:
        """Verify the session (``account.check``); False when logged out."""
        try:
            self.call("account.check", {})
            return True
        except InwxError:
            return False

    def _ensure_login(self) -> None:
        if not self._client._logged_in:
            self.login()

    # -- transport --
    def _raw(self, method: str, params: dict[str, Any]) -> Any:
        """POST one JSON-RPC call; return ``resData`` (raises on code != 1000)."""
        body = {"method": method, "params": dict(params or {})}
        if "lang" not in body["params"]:
            body["params"]["lang"] = self._client.config.language
        try:
            response = self._http.post(self._client.config.api_url, json=body)
        except InwxError:
            raise
        except Exception as e:
            raise InwxError(f"Request failed: {e}") from e
        if not response.content:
            raise InwxError(f"Empty response for {method}.", 0)
        try:
            payload = response.json()
        except Exception as e:
            raise InwxError(f"Invalid JSON response: {e}", response.status_code) from e
        if not isinstance(payload, dict) or "code" not in payload:
            raise InwxError(f"Unexpected response for {method}.", response.status_code, None, payload)
        try:
            code = int(payload.get("code", 0))
        except Exception:
            code = 0
        if code in (SUCCESS, PENDING, SESSION_END):
            return payload.get("resData")
        raise InwxError.from_response(payload)

    def call(self, method: str, params: dict[str, Any] | None = None, *, _retried: bool = False) -> Any:
        """Call ``method`` with ``params``; return ``resData`` (login first)."""
        self._ensure_login()
        try:
            return self._raw(method, dict(params or {}))
        except InwxError as e:
            if e.auth_failure and not _retried:
                logger.debug("auth failure on %s; re-login and retry once", method)
                self._client._logged_in = False
                self.login()
                return self.call(method, params, _retried=True)
            raise
