"""Authentication handler for OCI Registries with Bearer challenge negotiation."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx

AUTH_CHALLENGE_RE = re.compile(r'(\w+)="([^"]*)"')


class OCIAuthError(Exception):
    """Raised when authentication against an OCI registry fails."""
    pass


class OCIAuthManager:
    """Manages credentials and Bearer token acquisition for OCI registries."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._default_config_path()
        self._cached_tokens: Dict[str, str] = {}

    def _default_config_path(self) -> Path:
        docker_config = os.getenv("DOCKER_CONFIG")
        if docker_config:
            return Path(docker_config) / "config.json"
        return Path.home() / ".docker" / "config.json"

    def get_credentials(self, registry: str) -> Optional[Tuple[str, str]]:
        """Find username and password for a given registry from Docker config or environment."""
        # Check environment variables
        env_user = os.getenv("CAPSULE_REGISTRY_USER") or os.getenv("REGISTRY_USER")
        env_pass = os.getenv("CAPSULE_REGISTRY_PASSWORD") or os.getenv("REGISTRY_PASSWORD") or os.getenv("GITHUB_TOKEN")
        if env_user and env_pass:
            return env_user, env_pass

        # Check Docker config.json
        if self.config_path.is_file():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                auths = data.get("auths", {})

                # Check exact or normalized host matches
                candidates = [registry, f"https://{registry}", f"https://{registry}/v1/", f"https://{registry}/v2/"]
                if registry == "registry-1.docker.io":
                    candidates.extend(["https://index.docker.io/v1/", "index.docker.io", "docker.io"])

                for c in candidates:
                    if c in auths and "auth" in auths[c]:
                        raw = base64.b64decode(auths[c]["auth"]).decode("utf-8")
                        if ":" in raw:
                            user, pwd = raw.split(":", 1)
                            return user, pwd
            except Exception:
                pass
        return None

    def store_credentials(self, registry: str, username: str, secret: str) -> None:
        """Store credentials in Docker config."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict = {}
        if self.config_path.is_file():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        if "auths" not in data:
            data["auths"] = {}

        encoded = base64.b64encode(f"{username}:{secret}".encode("utf-8")).decode("utf-8")
        data["auths"][registry] = {"auth": encoded}
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def handle_auth_challenge(
        self,
        registry: str,
        challenge_header: str,
        scope: Optional[str] = None,
    ) -> Optional[str]:
        """Negotiate Bearer token from Www-Authenticate challenge header."""
        if not challenge_header:
            return None

        parts = dict(AUTH_CHALLENGE_RE.findall(challenge_header))
        realm = parts.get("realm")
        service = parts.get("service")
        req_scope = scope or parts.get("scope")

        if not realm:
            return None

        cache_key = f"{realm}:{service}:{req_scope}"
        if cache_key in self._cached_tokens:
            return f"Bearer {self._cached_tokens[cache_key]}"

        params: Dict[str, str] = {}
        if service:
            params["service"] = service
        if req_scope:
            params["scope"] = req_scope

        creds = self.get_credentials(registry)
        auth_header = None
        if creds:
            user, pwd = creds
            basic_encoded = base64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("utf-8")
            auth_header = f"Basic {basic_encoded}"

        headers = {"User-Agent": "Capsule-OCI-Client/0.5.0"}
        if auth_header:
            headers["Authorization"] = auth_header

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(realm, params=params, headers=headers)
            if resp.status_code != 200:
                raise OCIAuthError(
                    f"Authentication negotiation against '{realm}' failed (status {resp.status_code}): {resp.text}"
                )

            token_data = resp.json()
            token = token_data.get("token") or token_data.get("access_token")
            if not token:
                raise OCIAuthError(f"No token received from auth server: {resp.text}")

            self._cached_tokens[cache_key] = token
            return f"Bearer {token}"
