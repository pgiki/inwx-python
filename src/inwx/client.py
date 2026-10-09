"""Main INWX DomRobot client."""

from __future__ import annotations

from functools import cached_property
from typing import Self

import httpx
from dotenv import load_dotenv

from ._api.base import BaseAPI
from ._api.contacts import ContactsAPI
from ._api.dns import DnsAPI
from ._api.domains import DomainsAPI
from ._api.pricing import PricingAPI
from .config import Config
from .errors import ConfigurationError
from .logging import set_log_level


class Inwx:
    """
    The main INWX DomRobot client.

    Examples:
        >>> iw = Inwx()  # Loads INWX_USERNAME / INWX_PASSWORD from environment
        >>> iw = Inwx(username="...", password="...")  # Explicit
        >>> iw = Inwx.from_env_file(".env.prod")  # From specific env file
        >>> iw = Inwx(api_url="https://api.ote.domrobot.com/jsonrpc/")  # OTE sandbox

        >>> # Check domain availability (free call)
        >>> iw.domains.check("example.com")

        >>> # Use as context manager (logs out on exit)
        >>> with Inwx() as iw:
        ...     iw.domains.list()
    """

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        api_url: str | None = None,
        timeout: float | None = None,
        log_level: str | None = None,
        language: str | None = None,
    ) -> None:
        """
        Initialize the client with smart defaults.

        Args:
            username: INWX account username (or set INWX_USERNAME env var)
            password: INWX account password (or set INWX_PASSWORD env var)
            api_url: JSON-RPC endpoint (default: production; use the OTE URL for tests)
            timeout: Request timeout in seconds (default: 30.0)
            log_level: Logging level (default: INFO)
            language: API message language (default: en)

        Raises:
            ConfigurationError: If required configuration is missing
        """
        try:
            self.config = Config.from_env(
                username=username,
                password=password,
                api_url=api_url,
                timeout=timeout,
                log_level=log_level,
                language=language,
            )
            set_log_level(self.config.log_level)
        except Exception as e:
            raise ConfigurationError(
                "Failed to load configuration. Ensure you have set:\n"
                "- INWX_USERNAME\n"
                "- INWX_PASSWORD\n"
                "Or pass them as parameters to the client."
            ) from e

        self._http = httpx.Client(timeout=self.config.timeout)
        self._logged_in = False

    @classmethod
    def from_env_file(cls, path: str = ".env") -> Self:
        """Create a client from a specific env file."""
        load_dotenv(path)
        return cls()

    @cached_property
    def domains(self) -> DomainsAPI:
        """Domain availability, registration, renewal, transfer and settings."""
        return DomainsAPI(self)

    @cached_property
    def contacts(self) -> ContactsAPI:
        """Contact handle create/read/update (IDs used by domain operations)."""
        return ContactsAPI(self)

    @cached_property
    def dns(self) -> DnsAPI:
        """DNS zone + record management (INWX nameservers)."""
        return DnsAPI(self)

    @cached_property
    def pricing(self) -> PricingAPI:
        """TLD price catalog (register/renew/transfer per TLD)."""
        return PricingAPI(self)

    def close(self) -> None:
        """Log out (when logged in) and close the underlying HTTP client."""
        try:
            if self._logged_in:
                BaseAPI(self).logout()
        except Exception:
            pass
        finally:
            self._logged_in = False
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<Inwx(api_url={self.config.api_url!r})>"
