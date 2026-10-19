from pathlib import Path

import fastmcp


path = Path(fastmcp.__file__).parent / "server/auth/oauth_proxy/proxy.py"
source = path.read_text()
old = 'token_endpoint_url = f"{self.base_url}/token"'
new = 'token_endpoint_url = str(self.base_url).rstrip("/") + "/token"'
assert source.count(old) == 1, "Unexpected FastMCP source; refusing patch"
path.write_text(source.replace(old, new))
compile(path.read_text(), str(path), "exec")

for base in ("https://example.test", "https://example.test/", "https://example.test/oauth/"):
    value = str(base).rstrip("/") + "/token"
    assert "//token" not in value

print("OAuth endpoint normalization applied; authentication checks unchanged")
