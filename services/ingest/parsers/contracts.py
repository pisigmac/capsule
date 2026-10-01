"""
Cross-layer and cross-service contract linker.
Binds frontend API calls (fetch/axios) to backend HTTP route handlers and database models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from .typescript_parser import TsFileInfo


@dataclass
class HttpContract:
    route: str
    frontend_file: str
    backend_file: str
    backend_func: Optional[str] = None


class ContractLinker:
    """Matches frontend fetch endpoints against backend route tables."""

    def link_http_contracts(
        self,
        frontend_files: List[TsFileInfo],
        backend_routes: List[Dict[str, Any]],
    ) -> List[HttpContract]:
        contracts: List[HttpContract] = []
        route_map: Dict[str, Dict[str, Any]] = {
            r["path"].rstrip("/"): r for r in backend_routes if "path" in r
        }

        for fe in frontend_files:
            for ep in fe.http_endpoints:
                norm_ep = ep.rstrip("/")
                matched = route_map.get(norm_ep)
                if matched:
                    contracts.append(
                        HttpContract(
                            route=matched["path"],
                            frontend_file=fe.path,
                            backend_file=matched.get("file", ""),
                            backend_func=matched.get("func"),
                        )
                    )

        return contracts
