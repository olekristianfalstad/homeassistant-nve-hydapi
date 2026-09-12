"""Share station metadata and rate-limit state across setup and polling."""

from hashlib import sha256

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NveHydApiClient
from .const import DOMAIN


@callback
def get_client(hass: HomeAssistant, api_key: str) -> NveHydApiClient:
    """Reuse clients by key without placing plaintext credentials in cache keys."""
    clients = hass.data.setdefault(f"{DOMAIN}_clients", {})
    identity = sha256(api_key.encode()).hexdigest()
    if identity not in clients:
        if len(clients) >= 4:
            clients.pop(next(iter(clients)))
        clients[identity] = NveHydApiClient(async_get_clientsession(hass), api_key)
    return clients[identity]
