"""Offline tests for inwx-python (no network)."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from inwx import (
    ConfigurationError,
    Contact,
    Domain,
    Inwx,
    InwxError,
    NotSupportedError,
)
from inwx._api.domains import period_param
from inwx.idn import from_punycode, split_domain, to_punycode


def _client(**overrides):
    env = {"INWX_USERNAME": "user", "INWX_PASSWORD": "pass"}
    os.environ.update(env)
    kwargs = {"username": "user", "password": "pass"}
    kwargs.update(overrides)
    return Inwx(**kwargs)


def _rpc(code=1000, res_data=None, msg="Command completed successfully"):
    return SimpleNamespace(
        status_code=200,
        headers={},
        content=b'{"code":%d}' % code,
        json=(lambda: {"code": code, "msg": msg, "resData": res_data}),
    )


class _FakeApi:
    """Method-name dispatcher standing in for httpx.Client."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, **kwargs):
        body = kwargs.get("json") or {}
        method = body.get("method", "")
        self.calls.append((method, body.get("params") or {}))
        route = self.routes.get(method)
        if route is None:
            return _rpc(2000, None, f"Unknown command {method}")
        if callable(route):
            return route(self.calls[-1][1])
        return route

    def close(self):
        pass


def _transport(routes: dict):
    iw = _client()
    iw._http = _FakeApi(routes)
    return iw


def _contact_fields():
    return {
        "type": "PERSON",
        "name": "Example Testing",
        "street": "4 office",
        "city": "Lag",
        "pc": "110001",
        "cc": "NG",
        "voice": "+234.812345678",
        "email": "exam@gmail.com",
    }


def _session(**extra):
    return {
        "account.login": _rpc(1000, {"customerId": 1}),
        "account.logout": _rpc(1500, None, "Session ended"),
        **extra,
    }


# -- config / session --


def test_config_missing_raises():
    for k in ("INWX_USERNAME", "INWX_PASSWORD"):
        os.environ.pop(k, None)
    with pytest.raises(ConfigurationError):
        Inwx()
    os.environ.update({"INWX_USERNAME": "u", "INWX_PASSWORD": "p"})


def test_config_invalid_log_level():
    with pytest.raises(ConfigurationError):
        Inwx(username="u", password="p", log_level="VERBOSE")


def test_client_context_manager_logs_out():
    iw = _transport(_session(**{"domain.check": _rpc(1000, {"domain": []})}))
    with iw as ctx:
        assert ctx is iw
        ctx.domains.check("example.com")
    methods = [c[0] for c in iw._http.calls]
    assert methods[0] == "account.login"
    assert methods[-1] == "account.logout"


def test_login_sends_credentials_once():
    iw = _transport(
        _session(
            **{
                "domain.check": _rpc(1000, {"domain": [{"domain": "example.com", "avail": 1}]}),
            }
        )
    )
    iw.domains.check("example.com", "example.net")
    iw.domains.check("example.org")
    login_calls = [c for c in iw._http.calls if c[0] == "account.login"]
    assert len(login_calls) == 1
    assert login_calls[0][1]["user"] == "user"
    assert login_calls[0][1]["pass"] == "pass"
    assert login_calls[0][1]["lang"] == "en"


def test_auth_failure_relogs_in_once():
    iw = _client()
    seen = {"infos": 0}
    fake = _FakeApi(
        {
            "account.login": _rpc(1000, {"customerId": 1}),
            "account.logout": _rpc(1500, None),
            "domain.info": _rpc(1000, {"domain": "example.com", "transferLock": 1}),
        }
    )
    real_post = fake.post

    def flaky(url, **kwargs):
        body = kwargs.get("json") or {}
        if body.get("method") == "domain.info" and seen["infos"] == 0:
            seen["infos"] += 1
            fake.calls.append(("domain.info", body.get("params") or {}))
            return _rpc(2200, None, "Authentication error")
        return real_post(url, **kwargs)

    fake.post = flaky
    iw._http = fake
    assert iw.domains.get_lock("example.com") is True
    assert sum(1 for c in fake.calls if c[0] == "account.login") == 2


def test_error_from_code():
    iw = _transport(_session(**{"domain.info": _rpc(2303, None, "Object does not exist")}))
    with pytest.raises(InwxError) as exc_info:
        iw.domains.get_info("missing.example")
    assert exc_info.value.code == 2303
    assert "Object does not exist" in str(exc_info.value)


def test_error_details_flattened():
    err_body = {
        "code": 2003,
        "msg": "Parameter missing",
        "details": [{"code": "PARAM_MISSING", "msg": "email required"}],
    }
    iw = _transport(
        {
            "account.login": _rpc(1000, {}),
            "account.logout": _rpc(1500, None),
            "contact.create": SimpleNamespace(
                status_code=200, headers={}, content=b"x", json=lambda: err_body
            ),
        }
    )
    with pytest.raises(InwxError) as exc_info:
        iw.contacts.save({"name": "x"})
    assert "email required" in str(exc_info.value)


# -- availability --


def test_check_parses_rows():
    iw = _transport(
        _session(
            **{
                "domain.check": _rpc(
                    1000,
                    {
                        "domain": [
                            {"domain": "cool.ai", "avail": 1, "price": 69.99, "currency": "EUR"},
                            {"domain": "taken.com", "avail": 0, "status": "unavailable"},
                        ]
                    },
                )
            }
        )
    )
    rows = iw.domains.check("cool.ai", "taken.com")
    assert [r.domain for r in rows] == ["cool.ai", "taken.com"]
    assert [r.available for r in rows] == [True, False]
    assert str(rows[0].price) == "69.99"
    assert rows[1].result == "unavailable"
    method, params = iw._http.calls[1]
    assert method == "domain.check"
    assert params["domain"] == ["cool.ai", "taken.com"]


def test_check_single_no_result_raises():
    iw = _transport(_session(**{"domain.check": _rpc(1000, {"domain": []})}))
    with pytest.raises(ValueError):
        iw.domains.check_single("example.com")


def test_period_param():
    assert period_param(1) == "1Y"
    assert period_param(3) == "3Y"


# -- register / renew / transfer --


def _register_routes():
    return _session(
        **{
            "contact.list": _rpc(1000, {"count": 0, "contact": []}),
            "contact.create": _rpc(1000, {"id": 42}),
            "domain.create": _rpc(1000, {"roId": 7, "price": 10.0, "currency": "EUR"}),
            "domain.info": _rpc(
                1000,
                {"roId": 7, "domain": "example.com", "status": "ok", "ns": ["ns.inwx.de"]},
            ),
        }
    )


def test_register_ensures_contact_and_sends_ns():
    iw = _transport(_register_routes())
    out = iw.domains.register(
        "Example.COM",
        contact=_contact_fields(),
        years=2,
        nameservers=["ns1.example.net", "ns2.example.net"],
    )
    assert isinstance(out, Domain)
    assert out.name == "example.com"
    create = next(c for c in iw._http.calls if c[0] == "domain.create")
    assert create[1]["domain"] == "example.com"
    assert create[1]["period"] == "2Y"
    assert create[1]["ns"] == ["ns1.example.net", "ns2.example.net"]
    assert create[1]["transferLock"] == 1
    assert create[1]["registrant"] == 42
    contact_create = next(c for c in iw._http.calls if c[0] == "contact.create")
    assert contact_create[1]["email"] == "exam@gmail.com"


def test_renew_fetches_expiration():
    iw = _transport(
        _session(
            **{
                "domain.info": _rpc(1000, {"domain": "example.com", "exDate": "2026-10-01 00:00:00"}),
                "domain.renew": _rpc(1000, {"roId": 7}),
            }
        )
    )
    out = iw.domains.renew("example.com", years=2)
    assert isinstance(out, Domain)
    renew = next(c for c in iw._http.calls if c[0] == "domain.renew")
    assert renew[1] == {"domain": "example.com", "period": "2Y", "expiration": "2026-10-01", "lang": "en"}


def test_transfer_sends_authcode():
    iw = _transport(
        _session(
            **{
                "contact.list": _rpc(1000, {"count": 0, "contact": []}),
                "contact.create": _rpc(1000, {"id": 9}),
                "domain.transfer": _rpc(1000, {"roId": 8}),
                "domain.info": _rpc(1000, {"domain": "example.com"}),
            }
        )
    )
    iw.domains.transfer("example.com", contact=_contact_fields(), auth_code="ABC123")
    transfer = next(c for c in iw._http.calls if c[0] == "domain.transfer")
    assert transfer[1]["authCode"] == "ABC123"
    assert transfer[1]["registrant"] == 9


def test_lock_cycle_and_epp():
    iw = _transport(
        _session(
            **{
                "domain.update": _rpc(1000, {}),
                "domain.info": _rpc(1000, {"domain": "example.com", "transferLock": 0, "authCode": "s3cret"}),
            }
        )
    )
    assert iw.domains.lock("example.com") is False  # info reports unlocked; call still sent
    update = next(c for c in iw._http.calls if c[0] == "domain.update")
    assert update[1]["transferLock"] == 1
    assert iw.domains.get_auth_code("example.com") == "s3cret"


def test_call_relogin_retries_non_auth_rejection_once():
    answers = iter(
        [
            _rpc(2002, None, "Command use error"),
            _rpc(1000, {"domain": [{"domain": "example.com", "avail": 1}]}),
        ]
    )
    iw = _transport(
        _session(
            **{
                "account.login": _rpc(1000, {}),
                "domain.check": lambda params: next(answers),
            }
        )
    )
    rows = iw.domains.check("example.com")
    assert rows and rows[0].available is True
    checks = [c for c in iw._http.calls if c[0] == "domain.check"]
    assert len(checks) == 2
    logins = [c for c in iw._http.calls if c[0] == "account.login"]
    assert len(logins) == 2  # initial + re-login before retry


def test_call_raises_persistent_rejection_after_one_retry():
    iw = _transport(
        _session(
            **{
                "account.login": _rpc(1000, {}),
                "domain.check": _rpc(2002, None, "Command use error"),
            }
        )
    )
    with pytest.raises(InwxError) as excinfo:
        iw.domains.check("example.com")
    assert excinfo.value.code == 2002
    checks = [c for c in iw._http.calls if c[0] == "domain.check"]
    assert len(checks) == 2  # initial + exactly one retry


def test_set_privacy_sends_extdata():
    iw = _transport(_session(**{"domain.update": _rpc(1000, {})}))
    assert iw.domains.set_privacy("Example.COM", True) is True
    update = next(c for c in iw._http.calls if c[0] == "domain.update")
    assert update[1] == {
        "domain": "example.com",
        "extData": {"WHOIS-PROTECTION": True},
        "lang": "en",
    }
    assert iw.domains.set_privacy("example.com", False) is False
    updates = [c for c in iw._http.calls if c[0] == "domain.update"]
    assert updates[-1][1]["extData"] == {"WHOIS-PROTECTION": False}


def test_nameservers_roundtrip():
    iw = _transport(
        _session(
            **{
                "domain.info": _rpc(1000, {"domain": "example.com", "ns": ["ns.inwx.de", "ns2.inwx.de"]}),
                "domain.update": _rpc(1000, {}),
            }
        )
    )
    assert iw.domains.get_nameservers("example.com") == ["ns.inwx.de", "ns2.inwx.de"]
    assert iw.domains.set_nameservers("example.com", ["ns1.x", "ns2.x"]) == ["ns.inwx.de", "ns2.inwx.de"]
    update = next(c for c in iw._http.calls if c[0] == "domain.update")
    assert update[1]["ns"] == ["ns1.x", "ns2.x"]


def test_get_contacts_ids():
    iw = _transport(
        _session(
            **{
                "domain.info": _rpc(
                    1000, {"domain": "example.com", "registrant": 1, "admin": 1, "tech": 2, "billing": 1}
                ),
            }
        )
    )
    assert iw.domains.get_contacts("example.com") == {"registrant": 1, "admin": 1, "tech": 2, "billing": 1}


def test_list_paginates():
    iw = _transport(
        _session(**{"domain.list": _rpc(1000, {"count": 1, "domain": [{"roId": 7, "domain": "example.com"}]})})
    )
    (d,) = iw.domains.list(page=2, page_size=10)
    assert d.name == "example.com"
    _, params = next(c for c in iw._http.calls if c[0] == "domain.list")
    assert params["page"] == 2 and params["pagelimit"] == 10


# -- contacts --


def test_contacts_save_read_ensure():
    iw = _transport(
        _session(
            **{
                "contact.create": _rpc(1000, {"id": 42}),
                "contact.info": _rpc(1000, {"contact": {"id": 42, **_contact_fields()}}),
                "contact.list": _rpc(1000, {"count": 1, "contact": [{"id": 43, **_contact_fields()}]}),
            }
        )
    )
    assert iw.contacts.save(_contact_fields()) == 42
    assert iw.contacts.read(42).email == "exam@gmail.com"
    assert iw.contacts.ensure(_contact_fields()) == 43  # matched by email, no create
    assert iw.contacts.ensure({"id": 44}) == 44


def test_contact_model_api_fields():
    c = Contact.from_api({"roId": 5, **_contact_fields()})
    assert c.id == 5
    fields = c.api_fields()
    assert fields["cc"] == "NG" and fields["voice"] == "+234.812345678" and "id" not in fields


def test_contact_payload_defaults_type_for_dicts():
    """``contact.create`` requires ``type`` (2003 MISSING_TYPE otherwise)."""
    from inwx._api.contacts import _contact_payload

    fields = _contact_fields()
    del fields["type"]
    payload = _contact_payload(fields)
    assert payload["type"] == "PERSON"
    assert _contact_payload({**fields, "type": "org"})["type"] == "ORG"
    assert _contact_payload(Contact.from_profile(name="N", email="e@x.com"))["type"] == "PERSON"
    assert (
        _contact_payload(Contact.from_profile(name="N", email="e@x.com", organization="Acme"))["type"]
        == "ORG"
    )


# -- dns --


def _dns_routes():
    return _session(
        **{
            "nameserver.info": _rpc(
                1000,
                {
                    "roId": 3,
                    "domain": "example.com",
                    "record": [
                        {"id": "11", "name": "@", "type": "A", "content": "1.2.3.4", "ttl": 3600},
                        {"id": "12", "name": "www", "type": "A", "content": "1.2.3.4", "ttl": 3600},
                    ],
                },
            ),
            "nameserver.createRecord": _rpc(1000, {"id": "13"}),
            "nameserver.deleteRecord": _rpc(1000, {}),
        }
    )


def test_dns_list_and_create():
    iw = _transport(_dns_routes())
    rows = iw.dns.list("example.com")
    assert [r.fqdn("example.com") for r in rows] == ["example.com", "www.example.com"]
    created = iw.dns.create_record("example.com", "shop", "A", "5.6.7.8", ttl=300)
    assert created.name == "shop" and created.content == "5.6.7.8"
    _, params = next(c for c in iw._http.calls if c[0] == "nameserver.createRecord")
    assert params["type"] == "A" and params["ttl"] == 300


def test_dns_delete_filters():
    iw = _transport(_dns_routes())
    assert iw.dns.delete("example.com", record_type="A", name="www.example.com") == 1
    _, params = next(c for c in iw._http.calls if c[0] == "nameserver.deleteRecord")
    assert params["id"] == "12"


def test_dns_delete_matches_at_sign_to_fqdn_rows():
    routes = _dns_routes()
    routes["nameserver.info"] = _rpc(
        1000,
        {
            "roId": 3,
            "domain": "example.com",
            "record": [{"id": "11", "name": "example.com", "type": "A", "content": "1.2.3.4", "ttl": 3600}],
        },
    )
    iw = _transport(routes)
    assert iw.dns.delete("example.com", record_type="A", name="@") == 1
    _, params = next(c for c in iw._http.calls if c[0] == "nameserver.deleteRecord")
    assert params["id"] == "11"


def test_ensure_zone_sends_default_nameservers():
    from inwx._api.dns import DEFAULT_NAMESERVERS

    iw = _transport(
        {
            "account.login": _rpc(1000, {"customerId": 1}),
            "account.logout": _rpc(1500, None),
            "nameserver.info": _rpc(2303, None, "Object does not exist"),
            "nameserver.create": _rpc(1000, {"roId": 3}),
        }
    )
    # First info fails -> create with default NS -> second info succeeds.
    iw._http.routes["nameserver.info"] = _rpc(1000, {"roId": 3, "domain": "example.com", "record": []})
    calls = {"infos": 0}
    real = iw._http.post

    def flaky(url, **kwargs):
        body = kwargs.get("json") or {}
        # Fail the first two infos: the initial call and the one re-login
        # retry (a persistent 2303 means the zone is genuinely absent, so
        # ensure_zone must still fall through to create).
        if body.get("method") == "nameserver.info" and calls["infos"] < 2:
            calls["infos"] += 1
            iw._http.calls.append(("nameserver.info", body.get("params") or {}))
            return _rpc(2303, None, "Object does not exist")
        return real(url, **kwargs)

    iw._http.post = flaky
    iw.dns.ensure_zone("example.com")
    _, params = next(c for c in iw._http.calls if c[0] == "nameserver.create")
    assert params["ns"] == DEFAULT_NAMESERVERS


def test_dns_set_a_records():
    iw = _transport(_dns_routes())
    (created,) = iw.dns.set_a_records("example.com", "@", "9.9.9.9")
    assert created.content == "9.9.9.9"
    assert any(c[0] == "nameserver.deleteRecord" for c in iw._http.calls)


def test_dns_delete_zone():
    iw = _transport(_session(**{"nameserver.delete": _rpc(1000, {})}))
    iw.dns.delete_zone("example.com")
    method, params = iw._http.calls[1]
    assert method == "nameserver.delete"
    assert params["domain"] == "example.com"


# -- pricing / tld list --


def test_pricing_catalog():
    iw = _transport(
        _session(
            **{
                "domain.getPrices": _rpc(
                    1000,
                    {
                        "price": [
                            {"tld": "com", "currency": "EUR", "createPrice": 10.5, "renewalPrice": 11.0,
                             "transferPrice": 10.5},
                        ]
                    },
                )
            }
        )
    )
    (row,) = iw.pricing.catalog("com")
    assert row.tld == "com"
    assert str(row.register) == "10.5" and str(row.renew) == "11.0"
    _, params = next(c for c in iw._http.calls if c[0] == "domain.getPrices")
    assert params["tld"] == ["com"]


def test_get_tld_list():
    iw = _transport(_session(**{"domain.getRules": _rpc(1000, {"rules": [{"tld": "com"}, {"tld": "de"}]})}))
    assert iw.domains.get_tld_list() == ["com", "de"]


def test_unsupported_suggest():
    iw = _client()
    with pytest.raises(NotSupportedError):
        iw.domains.suggest("example.com")


def test_idn_helpers():
    assert to_punycode("Example.COM.") == "example.com"
    assert from_punycode("example.com") == "example.com"
    assert to_punycode("münchen.de") == "xn--mnchen-3ya.de"
    assert split_domain("example.com.ng") == ("example", "com.ng")
