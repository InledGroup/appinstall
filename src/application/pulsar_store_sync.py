"""
Pulsar Store sync service for appinstall/pkm.

Provides functionality to:
  - Sync the local catalog cache from store-os.inled.es
  - Check for updates to installed Pulsar Store packages
  - Show update notifications in the CLI
"""

import os
import json
import time
from typing import List, Dict, Optional

from src.infrastructure.adapters.pulsar_store_adapter import (
    PulsarStoreAdapter,
    CATALOG_CACHE,
    INSTALLED_DB,
    CACHE_DIR,
)


class PulsarStoreSync:
    """Manages catalog synchronization and update checking for the Pulsar Store."""

    def __init__(self):
        self.adapter = PulsarStoreAdapter()

    def sync_catalog(self, force: bool = False) -> Dict[str, any]:
        """Sync the local catalog from the remote store.

        Returns a summary dict with:
          - total: total packages in catalog
          - types: breakdown by package type
          - success: whether the sync succeeded
        """
        catalog = self.adapter._fetch_catalog(force=force)

        if not catalog:
            return {
                "total": 0,
                "types": {},
                "success": False,
                "error": "Failed to fetch catalog",
            }

        # Count by type
        types = {}
        for pkg in catalog:
            pkg_type = pkg.get("type", "unknown")
            types[pkg_type] = types.get(pkg_type, 0) + 1

        return {
            "total": len(catalog),
            "types": types,
            "success": True,
        }

    def check_updates(self) -> List[Dict[str, str]]:
        """Check for updates to installed Pulsar Store packages.

        Returns a list of dicts with:
          - id: package ID
          - name: package name
          - installed_version: current installed version
          - latest_version: latest version in catalog
          - has_update: whether an update is available
        """
        installed_db = self._load_installed_db()
        if not installed_db:
            return []

        catalog = self.adapter._get_catalog()
        catalog_map = {pkg.get("id"): pkg for pkg in catalog}

        updates = []
        for pkg_id, installed_info in installed_db.items():
            installed_version = installed_info.get("version", "0.0.0")
            catalog_pkg = catalog_map.get(pkg_id)

            if catalog_pkg:
                latest_version = catalog_pkg.get("version", installed_version)
                has_update = self._version_newer(latest_version, installed_version)
                updates.append({
                    "id": pkg_id,
                    "name": catalog_pkg.get("name", pkg_id),
                    "installed_version": installed_version,
                    "latest_version": latest_version,
                    "has_update": has_update,
                })

        return updates

    def get_catalog_summary(self) -> Dict[str, any]:
        """Get a summary of the Pulsar Store catalog."""
        catalog = self.adapter._get_catalog()

        types = {}
        for pkg in catalog:
            pkg_type = pkg.get("type", "unknown")
            types[pkg_type] = types.get(pkg_type, 0) + 1

        return {
            "total": len(catalog),
            "types": types,
            "last_sync": self._get_last_sync_time(),
        }

    def _load_installed_db(self) -> Dict[str, dict]:
        if os.path.exists(INSTALLED_DB):
            try:
                with open(INSTALLED_DB, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_last_sync_time(self) -> Optional[float]:
        if os.path.exists(CATALOG_CACHE):
            return os.path.getmtime(CATALOG_CACHE)
        return None

    @staticmethod
    def _version_newer(v1: str, v2: str) -> bool:
        """Simple version comparison: returns True if v1 > v2."""
        try:
            parts1 = [int(x) for x in v1.split(".") if x.isdigit()]
            parts2 = [int(x) for x in v2.split(".") if x.isdigit()]
            # Pad shorter list with zeros
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            return parts1 > parts2
        except Exception:
            return False
