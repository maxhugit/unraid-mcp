import json
from pathlib import Path

from fastmcp import Client
from fastmcp.server.auth.oidc_proxy import OIDCProxy
from fastmcp.server.providers.proxy import FastMCPProxy


cfg = json.loads(Path("/run/config/gateway.json").read_text())

auth = OIDCProxy(
    config_url=cfg["discovery_url"],
    client_id=cfg["client_id"],
    client_secret=cfg["client_secret"],
    base_url=cfg["base_url"],
    required_scopes=cfg.get("required_scopes", ["openid", "offline_access"]),
    jwt_signing_key=cfg["signing_key"],
    allowed_client_redirect_uris=cfg["allowed_client_redirect_uris"],
    require_authorization_consent=True,
)


def client_factory():
    return Client(cfg["backend_url"], auth=cfg["backend_token"])


server = FastMCPProxy(name="Unraid MCP", client_factory=client_factory, auth=auth)
server.run(
    transport="http",
    host=cfg["listen_host"],
    port=int(cfg["listen_port"]),
)
