"""Live check of the Afore client's token handling - no Home Assistant needed.

Stubs homeassistant/async_timeout so afore.py itself can run outside HA, then
drives it against the real portal to prove the refresh flow end to end:

    AFORE_REFRESH_TOKEN="<refresh JWT>" python3 client_auth_test.py

Complements refresh_token_test.py, which probes the bare OAuth endpoint; this
exercises the integration code that consumes it.


Reads the refresh token from AFORE_REFRESH_TOKEN; never writes it to disk.
"""
import asyncio
import contextlib
import os
import sys
import types

# --- stub async_timeout -----------------------------------------------------
at = types.ModuleType("async_timeout")


@contextlib.asynccontextmanager
async def _timeout(delay):
    async with asyncio.timeout(delay):
        yield


at.timeout = _timeout
sys.modules["async_timeout"] = at

# --- stub homeassistant -----------------------------------------------------
ha = types.ModuleType("homeassistant")
core = types.ModuleType("homeassistant.core")
cfg = types.ModuleType("homeassistant.config_entries")
const = types.ModuleType("homeassistant.const")
helpers = types.ModuleType("homeassistant.helpers")
comps = types.ModuleType("homeassistant.components")
pn = types.ModuleType("homeassistant.components.persistent_notification")
pn.async_create = lambda *a, **k: print("   [notification]", (a[2] if len(a) > 2 else k.get("title")))
pn.async_dismiss = lambda *a, **k: None
comps.persistent_notification = pn


class HomeAssistant:
    def __init__(self):
        self.config_entries = self


class ConfigEntry:
    """Mimics the real entry: data is immutable, updates go through hass."""

    def __init__(self, data):
        self.data = dict(data)


core.HomeAssistant = HomeAssistant
cfg.ConfigEntry = ConfigEntry
const.CONF_ACCESS_TOKEN = "access_token"
const.Platform = types.SimpleNamespace(SENSOR="sensor")
for name, mod in [
    ("homeassistant", ha),
    ("homeassistant.core", core),
    ("homeassistant.config_entries", cfg),
    ("homeassistant.const", const),
    ("homeassistant.helpers", helpers),
    ("homeassistant.components", comps),
    ("homeassistant.components.persistent_notification", pn),
]:
    sys.modules[name] = mod

# afore.py uses relative imports, so load it as part of a synthetic package
# rather than executing __init__.py (which would drag in the HA coordinator).
import pathlib  # noqa: E402

pkg = types.ModuleType("afore3")
pkg.__path__ = [str(pathlib.Path(__file__).resolve().parent)]
sys.modules["afore3"] = pkg

# Stand in for the pydantic models so this stays a test of token handling, not
# of whichever pydantic major version happens to be installed.
models = types.ModuleType("afore3.models")


class _Record:
    def __init__(self, **fields):
        self.__dict__.update(fields)


models.Status = type("Status", (_Record,), {})
models.System = type("System", (_Record,), {})
sys.modules["afore3.models"] = models

from afore3.afore import Afore, AforeAuthenticationError  # noqa: E402

token_expires_at = Afore._token_expiry

REFRESH = os.environ["AFORE_REFRESH_TOKEN"]
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"


class FakeHass(HomeAssistant):
    """Records async_update_entry calls the way HA would apply them."""

    def __init__(self):
        self.config_entries = self
        self.updates = 0

    def async_update_entry(self, entry, data):
        entry.data = dict(data)
        self.updates += 1


def fingerprint(tok):
    return f"...{tok[-8:]}" if tok else None


async def main():
    hass = FakeHass()
    results = []

    # 1. Only a refresh token, as the config flow now supplies it.
    entry = ConfigEntry({REFRESH_TOKEN: REFRESH})
    client = Afore(hass=hass, config_entry=entry)
    system = await client.system()
    minted = entry.data.get(ACCESS_TOKEN)
    results.append(("mints access token from refresh token alone", bool(minted)))
    results.append(("persisted via async_update_entry", hass.updates == 1))
    results.append(("returned live data", getattr(system, "id", None) is not None))
    print(f"   station id={system.id} name={system.name!r} "
          f"power={system.generationPower} today={system.generationValue}")
    print(f"   new access token {fingerprint(minted)} expires {token_expires_at(minted)}")
    print(f"   expirationDate stamped on model: {system.expirationDate}")

    # The portal hands back a rotated refresh token string; the client must
    # persist the newest one rather than keep replaying the original.
    rotated = entry.data[REFRESH_TOKEN]
    print(f"   refresh token {fingerprint(REFRESH)} -> {fingerprint(rotated)}")
    results.append(("persists the rotated refresh token", rotated != REFRESH))

    # 2. A valid access token must be reused, not needlessly refreshed.
    before = hass.updates
    await client.system()
    results.append(("reuses still-valid access token", hass.updates == before))

    # 3. A garbage/expired access token must be silently renewed.
    entry.data = {ACCESS_TOKEN: "not.a.jwt", REFRESH_TOKEN: REFRESH}
    client2 = Afore(hass=hass, config_entry=entry, session=client.session)
    system = await client2.system()
    results.append(("recovers from an unreadable access token", system.id is not None))

    # 4. A bad refresh token must surface as an auth error -> HA reauth flow.
    bad = ConfigEntry({REFRESH_TOKEN: "bogus-refresh-token"})
    client3 = Afore(hass=hass, config_entry=bad, session=client.session)
    try:
        await client3.system()
    except AforeAuthenticationError as err:
        results.append(("bad refresh token -> AforeAuthenticationError", True))
        print(f"   error text: {err}")
    except Exception as err:  # noqa: BLE001
        results.append((f"bad refresh token -> got {type(err).__name__}", False))
    else:
        results.append(("bad refresh token -> no error raised", False))

    # 5. The config flow validates against a plain stand-in, not a real entry:
    #    tokens must land in its .data without touching hass.config_entries.
    class ValidationEntry:  # mirrors config_flow._ValidationEntry
        def __init__(self, data):
            self.data = data

    stand_in = ValidationEntry({REFRESH_TOKEN: entry.data[REFRESH_TOKEN]})
    before = hass.updates
    client4 = Afore(hass=hass, config_entry=stand_in, session=client.session)
    system = await client4.system()
    results.append(
        (
            "config-flow stand-in captures tokens without hass",
            bool(stand_in.data.get(ACCESS_TOKEN)) and hass.updates == before,
        )
    )
    results.append(("config-flow stand-in returns live data", system.id is not None))

    await client.close()

    print()
    ok = True
    for name, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok &= passed
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


sys.exit(asyncio.run(main()))
