"""
Pulsar Store adapter for appinstall/pkm.

Fetches the package catalog from store-os.inled.es (schema/index.json)
and allows searching, installing, and managing Pulsar OS packages as
a first-class source alongside Flatpak, Snap, AUR, etc.

Package types supported:
  - flatpak:          Installed via `flatpak install`
  - gnome_extension:  Installed via the Pulsar Store scheme handler
  - sayri_skill:      Installed via the Pulsar Store scheme handler
  - sayri_plugin:     Installed via the Pulsar Store scheme handler
"""

import os
import json
import subprocess
import shutil
import tempfile
import hashlib
from typing import List, Dict, Optional
from src.domain.ports import PackageManager
from src.utils.system import get_cached_icon

# ── Catalog URL & local cache ───────────────────────────────────────────────
CATALOG_URL = "https://store-os.inled.es/schema/index.json"
CACHE_DIR = os.path.expanduser("~/.cache/appinstall/pulsar-store")
CATALOG_CACHE = os.path.join(CACHE_DIR, "index.json")
INSTALLED_DB = os.path.join(CACHE_DIR, "installed.json")
CACHE_TTL_SECONDS = 3600  # 1 hour


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_installed_db() -> Dict[str, dict]:
    """Load the local installed-packages database."""
    if os.path.exists(INSTALLED_DB):
        try:
            with open(INSTALLED_DB, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_installed_db(db: Dict[str, dict]):
    _ensure_cache_dir()
    with open(INSTALLED_DB, "w") as f:
        json.dump(db, f, indent=2)


class PulsarStoreAdapter(PackageManager):
    """Adapter that integrates the Pulsar Store catalog into pkm/appinstall."""

    def __init__(self):
        self._catalog: Optional[List[dict]] = None
        self._meta_cache: Dict[str, dict] = {}

    # ── Availability ────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """The Pulsar Store is always available (remote catalog)."""
        return True

    # ── Catalog fetching ────────────────────────────────────────────────────

    def _fetch_catalog(self, force: bool = False) -> List[dict]:
        """Download and cache the Pulsar Store catalog.

        Returns the list of package dicts from schema/index.json.
        Uses a local file cache with TTL to avoid hammering the server.
        """
        import time
        import requests

        _ensure_cache_dir()

        # Return cached catalog if fresh enough
        if not force and os.path.exists(CATALOG_CACHE):
            age = time.time() - os.path.getmtime(CATALOG_CACHE)
            if age < CACHE_TTL_SECONDS:
                try:
                    with open(CATALOG_CACHE, "r") as f:
                        data = json.load(f)
                    return data.get("packages", [])
                except Exception:
                    pass

        # Fetch fresh catalog
        try:
            headers = {"User-Agent": "pkm-pulsar-store/1.0"}
            r = requests.get(CATALOG_URL, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Write to cache
                with open(CATALOG_CACHE, "w") as f:
                    json.dump(data, f, indent=2)
                return data.get("packages", [])
        except Exception as e:
            print(f"Pulsar Store catalog fetch error: {e}")

        # Fallback: try stale cache
        if os.path.exists(CATALOG_CACHE):
            try:
                with open(CATALOG_CACHE, "r") as f:
                    data = json.load(f)
                return data.get("packages", [])
            except Exception:
                pass

        return []

    def _get_catalog(self) -> List[dict]:
        if self._catalog is None:
            self._catalog = self._fetch_catalog()
        return self._catalog

    # ── Search ──────────────────────────────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, str]]:
        """Search the Pulsar Store catalog by name, description, or ID."""
        catalog = self._get_catalog()
        if not catalog:
            return []

        query_lower = query.lower()
        results = []

        for pkg in catalog:
            name = pkg.get("name", "")
            desc = pkg.get("description", "")
            pkg_id = pkg.get("id", "")
            pkg_type = pkg.get("type", "")

            # Match against name, description, or ID
            if (query_lower in name.lower() or
                query_lower in desc.lower() or
                query_lower in pkg_id.lower()):

                # Map type to human-readable label
                type_label = {
                    "flatpak": "Flatpak App",
                    "gnome_extension": "GNOME Extension",
                    "sayri_skill": "Sayri Skill",
                    "sayri_plugin": "Sayri Plugin",
                }.get(pkg_type, pkg_type)

                version = pkg.get("version", "1.0")
                author = pkg.get("author", "Pulsar")

                # Cache metadata for fast info lookups
                self._meta_cache[pkg_id] = {
                    "name": name,
                    "description": desc,
                    "version": version,
                    "author": author,
                    "type": pkg_type,
                    "type_label": type_label,
                    "icon_url": pkg.get("icon_url", ""),
                    "download_url": pkg.get("download_url", ""),
                    "github_url": pkg.get("github_url", ""),
                    "readme_url": pkg.get("readme_url", ""),
                    "security_report": pkg.get("security_report", {}),
                    "metadata": pkg.get("metadata", {}),
                }

                # Build icon path (local cache)
                icon_url = pkg.get("icon_url", "")
                icon_path = ""
                if icon_url:
                    icon_path = get_cached_icon(icon_url, f"pulsar_{pkg_id}")

                results.append({
                    "name": pkg_id,
                    "display_name": name,
                    "desc": f"[{type_label}] {desc}" if desc else type_label,
                    "source": "pulsar",
                    "icon": icon_path if icon_path else "system-software-install-symbolic",
                    "version": version,
                    "author": author,
                })

        return results

    # ── List installed ──────────────────────────────────────────────────────

    def list_installed(self) -> List[str]:
        """List Pulsar Store packages that have been installed via pkm."""
        db = _load_installed_db()
        return list(db.keys())

    # ── Install ─────────────────────────────────────────────────────────────

    def install(self, package: str) -> List[str]:
        """Install a Pulsar Store package.

        For Flatpak packages: delegates to `flatpak install`.
        For other types: opens the Pulsar Store scheme handler
        (pulsar://install/<id>) which the desktop environment handles.
        """
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package)
        if not pkg:
            return ["sh", "-c", f"echo 'Package {package} not found in Pulsar Store'"]

        pkg_type = pkg.get("type", "")
        download_url = pkg.get("download_url", "")
        pkg_id = pkg.get("id", package)

        if pkg_type == "flatpak" and download_url:
            # Flatpak packages can be installed via flatpak directly
            # The download_url points to a .flatpakref or .flatpak file
            if download_url.endswith(".flatpakref") or download_url.endswith(".flatpak"):
                return ["pkexec", "flatpak", "install", "-y", download_url]
            # If it's a Flathub app ID, try flatpak install from flathub
            if download_url.startswith("https://flathub.org") or "flathub" in download_url.lower():
                return ["pkexec", "flatpak", "install", "-y", "flathub", package]

        # For all other types, use the scheme handler
        return ["sh", "-c", f"xdg-open 'pulsar://install/{pkg_id}' && "
                f"echo 'Opening Pulsar Store to install {pkg_id}...'"]

    def install_multiple(self, packages: List[str]) -> List[str]:
        """Install multiple Pulsar Store packages."""
        commands = []
        for pkg in packages:
            commands.extend(self.install(pkg))
        return commands

    def install_local(self, file_path: str) -> List[str]:
        """Install a local Pulsar Store package file (.zip)."""
        if file_path.endswith(".zip"):
            return ["sh", "-c", f"xdg-open 'pulsar://install-local/{file_path}'"]
        return ["sh", "-c", f"echo 'Unsupported file type: {file_path}'"]

    # ── Uninstall ───────────────────────────────────────────────────────────

    def uninstall(self, package: str) -> List[str]:
        """Uninstall a Pulsar Store package.

        For Flatpak: delegates to `flatpak uninstall`.
        For others: opens the scheme handler or uses the Pulsar Store CLI.
        """
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package)
        if not pkg:
            return ["sh", "-c", f"echo 'Package {package} not found in Pulsar Store'"]

        pkg_type = pkg.get("type", "")

        if pkg_type == "flatpak":
            return ["pkexec", "flatpak", "uninstall", "-y", package]

        # For Sayri skills/plugins, use the pulsar-store CLI
        return ["sh", "-c", f"pulsar-store remove '{package}' 2>/dev/null || "
                f"echo 'Use pulsar-store remove {package} to uninstall'"]

    # ── Package info ────────────────────────────────────────────────────────

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        """Get detailed info for a Pulsar Store package."""
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package_name)

        if not pkg:
            return {
                "name": package_name,
                "version": "N/A",
                "description": "Package not found in Pulsar Store.",
                "source": "pulsar",
                "icon": "system-software-install-symbolic",
            }

        pkg_type = pkg.get("type", "")
        type_label = {
            "flatpak": "Flatpak App",
            "gnome_extension": "GNOME Extension",
            "sayri_skill": "Sayri Skill",
            "sayri_plugin": "Sayri Plugin",
        }.get(pkg_type, pkg_type)

        security = pkg.get("security_report", {})
        security_score = security.get("score", "N/A")
        security_status = security.get("status", "N/A")

        info = {
            "name": pkg.get("name", package_name),
            "version": pkg.get("version", "N/A"),
            "description": pkg.get("description", ""),
            "source": "pulsar",
            "developer": pkg.get("author", ""),
            "license": "Open Source",
            "size": "N/A",
            "icon": "system-software-install-symbolic",
            "pulsar_type": type_label,
            "pulsar_id": pkg.get("id", package_name),
            "security_score": str(security_score),
            "security_status": security_status,
        }

        # Enrich with icon
        icon_url = pkg.get("icon_url", "")
        if icon_url:
            cached = get_cached_icon(icon_url, f"pulsar_{package_name}")
            if cached:
                info["icon"] = cached

        # Add website/source repo
        github_url = pkg.get("github_url", "")
        if github_url:
            info["website"] = github_url

        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        """Get info for a local Pulsar Store package file."""
        return {
            "name": os.path.basename(file_path),
            "version": "N/A",
            "description": "Pulsar Store package file.",
            "size": f"{os.path.getsize(file_path) / (1024*1024):.1f} MB" if os.path.exists(file_path) else "N/A",
            "icon": "system-software-install-symbolic",
            "source": "pulsar",
        }

    # ── System methods (no-ops for remote catalog) ──────────────────────────

    def update_cache(self) -> List[str]:
        """Refresh the local catalog cache."""
        return ["sh", "-c", f"rm -f '{CATALOG_CACHE}' && echo 'Pulsar Store cache cleared'"]

    def clean_cache(self) -> List[str]:
        return ["sh", "-c", f"rm -rf '{CACHE_DIR}' && echo 'Pulsar Store cache cleaned'"]

    def autoremove(self) -> List[str]:
        return []

    def fix_broken(self) -> List[str]:
        return []

    def get_cache_directory(self) -> str:
        return CACHE_DIR

    def install_clamav(self) -> List[str]:
        return []

    def upgrade_system(self) -> List[str]:
        """Check for Pulsar Store updates."""
        return ["sh", "-c", "pulsar-store check 2>/dev/null || echo 'pulsar-store CLI not installed'"]

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _find_pkg(self, catalog: List[dict], pkg_id: str) -> Optional[dict]:
        """Find a package by ID in the catalog."""
        for pkg in catalog:
            if pkg.get("id") == pkg_id:
                return pkg
        # Try name match as fallback
        for pkg in catalog:
            if pkg.get("name", "").lower() == pkg_id.lower():
                return pkg
        return None

    def mark_installed(self, package: str, version: str = ""):
        """Mark a package as installed in the local database."""
        db = _load_installed_db()
        db[package] = {
            "version": version,
            "installed_at": __import__("time").time(),
        }
        _save_installed_db(db)

    def mark_uninstalled(self, package: str):
        """Remove a package from the installed database."""
        db = _load_installed_db()
        db.pop(package, None)
        _save_installed_db(db)
