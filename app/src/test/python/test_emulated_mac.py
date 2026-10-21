"""
The two Python halves of signing in as the emulated Mac.

**Against the real `AppleAccount`**, with only Grand Slam's answers replaced: the 409 shim works
by replacing `_gsa_request` on the instance, and a fake account would keep that name after a
rename (rule 3).

**Not covered here:** that the library, given `au`, then asks for a code. That decision is in
`_gsa_authenticate` after the SRP exchange, which needs Apple's half to reach. It is the line
`if au in ("secondaryAuth", "trustedDeviceSecondaryAuth")` in the pinned `account.py`.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from findmy.reports import AppleAccount, RemoteAnisetteProvider

import account_loop
import main


class Bridge:
    """What Java hands Python as `localAnisette`, as far as these tests need."""

    def __init__(self, router: str | None = None) -> None:
        if router is not None:
            self.router = lambda: router

    def otp(self) -> str:
        return "b3Rw"

    def machine(self) -> str:
        return "bWFjaGluZQ=="


class TestTheRoutingNumber:
    def test_it_is_the_one_java_reports(self) -> None:
        provider = main.LocalAnisetteProvider(Bridge(router="12345678"), "https://example.invalid")
        assert provider.router == "12345678"

    def test_a_bridge_without_one_keeps_the_librarys(self) -> None:
        provider = main.LocalAnisetteProvider(Bridge(), "https://example.invalid")
        assert provider.router == RemoteAnisetteProvider("https://example.invalid").router


def anAccount() -> AppleAccount:
    made = AppleAccount(RemoteAnisetteProvider("https://example.invalid"))
    assert account_loop.attach(made)
    return made


def answersFromGrandSlam(account: AppleAccount, complete: dict[str, Any]) -> list[dict]:
    """
    Make the account's Grand Slam exchange answer `init` and then `complete` with `complete`,
    without SRP: the password check itself is replaced, because it needs Apple's half.
    """
    asked: list[dict] = []
    inner = account._asyncacc

    async def gsa_request(parameters: dict[str, Any]) -> dict[str, Any]:
        asked.append(parameters)
        return {"Status": dict(complete)}

    inner._gsa_request = gsa_request
    return asked


class TestHsc409WithNoAu:
    def test_a_complete_answered_409_without_au_is_read_as_a_second_factor(self) -> None:
        account = anAccount()
        try:
            asked = answersFromGrandSlam(account, {"ec": 0, "hsc": 409})
            main._treatHsc409AsSecondFactor(account)

            response = asyncio.run(account._asyncacc._gsa_request({"o": "complete"}))

            assert asked == [{"o": "complete"}]
            assert response["Status"]["au"] == "trustedDeviceSecondaryAuth"
        finally:
            account_loop.detach(account)

    @pytest.mark.parametrize("status", [
        {"ec": 0, "hsc": 200},
        {"ec": 0, "hsc": 409, "au": "secondaryAuth"},
    ])
    def test_anything_else_is_left_as_apple_sent_it(self, status: dict) -> None:
        account = anAccount()
        try:
            answersFromGrandSlam(account, status)
            main._treatHsc409AsSecondFactor(account)

            response = asyncio.run(account._asyncacc._gsa_request({"o": "complete"}))

            assert response["Status"] == status
        finally:
            account_loop.detach(account)

    def test_an_init_answered_409_is_not_touched(self) -> None:
        account = anAccount()
        try:
            answersFromGrandSlam(account, {"ec": 0, "hsc": 409})
            main._treatHsc409AsSecondFactor(account)

            response = asyncio.run(account._asyncacc._gsa_request({"o": "init"}))

            assert "au" not in response["Status"]
        finally:
            account_loop.detach(account)

class TestWhenTheInternalsMove:
    def test_an_account_without_gsa_request_is_left_alone(self, capsys) -> None:
        account = SimpleNamespace(_asyncacc=SimpleNamespace())
        main._treatHsc409AsSecondFactor(account)  # type: ignore[arg-type]
        assert "hsc 409 will not be read as 2FA" in capsys.readouterr().out
