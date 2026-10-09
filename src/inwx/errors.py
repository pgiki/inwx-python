"""INWX DomRobot API error handling.

Result codes (apidoc chapter 4): ``1000`` ok, ``1001`` ok-pending,
``200x`` request errors, ``210x`` eligibility/billing, ``22xx/23xx``
auth/association errors, ``24xx/25xx`` transport/session errors.
"""

from __future__ import annotations

from typing import Any

SUCCESS = 1000
PENDING = 1001
SESSION_END = 1500

AUTH_CODES = {1200, 2200, 2201, 2202, 2501}


class InwxError(Exception):
    """Base exception for all INWX DomRobot API errors."""

    def __init__(
        self,
        message: str,
        code: int = 0,
        reason: str | None = None,
        details: Any | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.reason = reason or ""
        self.details = details
        self.status_code = code
        # Aliases matching the sibling SDKs' error shapes.
        self.response_text = message
        super().__init__(str(self))

    def __str__(self) -> str:
        prefix = f"INWX API error {self.code}" if self.code else "INWX API error"
        if self.reason:
            return f"{prefix} [{self.reason}]: {self.message}"
        return f"{prefix}: {self.message}"

    @property
    def auth_failure(self) -> bool:
        return self.code in AUTH_CODES

    @classmethod
    def from_response(cls, data: Any) -> InwxError:
        """Build an error from a JSON-RPC response body."""
        if isinstance(data, dict):
            code = data.get("code", 0)
            try:
                code = int(code)
            except Exception:
                code = 0
            message = data.get("msg") or data.get("message") or f"DomRobot error {code}"
            reason = data.get("reasonCode") or data.get("reason") or ""
            details = data.get("details")
            if details and isinstance(details, list):
                extra = "; ".join(str(d.get("msg") if isinstance(d, dict) else d) for d in details)
                if extra:
                    message = f"{message}: {extra}"
            return cls(str(message), code, str(reason or "") or None, data)
        return cls(str(data) if data else "DomRobot error", 0, None, data)


class ConfigurationError(Exception):
    """Raised when client configuration is invalid."""

    pass


class NotSupportedError(Exception):
    """Raised when an operation has no INWX endpoint.

    Carries an ``alternative`` hint pointing at the supported way to
    achieve the same result.
    """

    def __init__(self, message: str, alternative: str = "") -> None:
        self.alternative = alternative
        super().__init__(f"{message} Alternative: {alternative}" if alternative else message)
