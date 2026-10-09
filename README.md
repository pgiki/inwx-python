# inwx-python

A friendly Python SDK for the [INWX DomRobot API](https://account.inwx.de/en/help/apidoc)
(domains, contacts, DNS, pricing).

Mirrors the `spaceship-python` / `resellercotz-python` / `go54-python` surface where
possible so it plugs into fikashop as an additional registrar + DNS provider.

```python
from inwx import Inwx

iw = Inwx()  # reads INWX_USERNAME / INWX_PASSWORD from env
checks = iw.domains.check("example.com", "shop.de")
print([(c.domain, c.available, c.price) for c in checks])
```

## Install

```bash
pip install inwx-python
```

Requires Python ≥ 3.12. Dependencies: `httpx`, `pydantic`, `python-dotenv`.

## Authentication

Use your INWX account username + password (API access must be enabled on the
account; no 2FA/TOTP supported by this SDK — use an account without it):

```bash
INWX_USERNAME=...
INWX_PASSWORD=...
#INWX_API_URL=https://api.domrobot.com/jsonrpc/  # default (production)
```

```python
iw = Inwx(username="...", password="...")
iw = Inwx.from_env_file(".env.prod")
iw = Inwx(api_url="https://api.ote.domrobot.com/jsonrpc/")  # free OTE sandbox
```

The client logs in lazily on the first call (cookie session), re-logs in once
after an auth failure, and logs out when used as a context manager.

## Examples

Runnable scripts in `examples/` (run from the repo root, e.g.
`python examples/quickstart.py`). ⚠️ marks scripts that can spend money or
mutate live state — those require explicit confirmation. Point `INWX_API_URL`
at the OTE sandbox to run everything for free:

| Script | What it shows |
|---|---|
| `quickstart.py` | Availability check (free). |
| `check_availability.py` | Bulk checks with premium pricing. |
| `domain_lifecycle.py` ⚠️ | `register/renew/transfer` (charged on prod) + `info`; dry-run by default, `--apply` + YES to write. |
| `contacts.py` | Handle create/read/ensure. |
| `dns_manage.py` ⚠️ | Zone list/record create; dry-run by default, `--apply` to write. |
| `pricing.py` | TLD price catalog (register/renew/transfer). |
| `error_handling.py` | Error shapes, unsupported endpoints (offline). |

## Endpoint coverage

JSON-RPC `domain.*`: `check` (batch, with premium pricing), `createregister`,
`renew` (current expiry auto-fetched), `transfer`, `update`, `trade` (owner
change), `restore`, `info`, `list` (paginated), `whois`, contacts
(get/set by handle id), nameservers (get/set), lock (`transferLock`),
`get_auth_code`, `set_autorenew` (renewalMode), `get_tld_list` (via
`domain.getRules`).

Contacts (`contact.*`): `save/read/update/delete/list/ensure` (find-by-email
or create; handles mirrored into all four domain roles by default).

DNS (`nameserver.*`): zone `status/ensure_zone/list_zones`, record
`list/create_record/update_record/delete_record/delete/set_a_records`.

Pricing (`domain.getPrices/getdomainprice`): `catalog(*tlds)`, `get_price()`.

Not wrapped (raise `NotSupportedError`): `suggest()` (no endpoint),
`domain.delete`/`push` (deliberately omitted — destructive/account moves).

## Testing

Fully offline (mock transport, no network, no spend):

```bash
pytest
ruff check src/ tests/
```
