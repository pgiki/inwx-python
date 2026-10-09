"""inwx-python — a friendly Python SDK for the INWX DomRobot API.

Example:
    >>> from inwx import Inwx
    >>> iw = Inwx()  # auto-loads INWX_USERNAME / INWX_PASSWORD from environment
    >>> checks = iw.domains.check("example.com")
    >>> [(c.domain, c.available, c.price) for c in checks]
"""

from __future__ import annotations

from .client import Inwx
from .config import Config
from .errors import (
    ConfigurationError,
    InwxError,
    NotSupportedError,
)
from .models import (
    Contact,
    DNSRecord,
    Domain,
    DomainCheck,
    TldPrice,
)

__version__ = "0.1.0"
__all__ = [
    "Config",
    "ConfigurationError",
    "Contact",
    "DNSRecord",
    "Domain",
    "DomainCheck",
    "Inwx",
    "InwxError",
    "NotSupportedError",
    "TldPrice",
]
