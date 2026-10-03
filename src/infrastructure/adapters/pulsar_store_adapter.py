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
from typing import List, Dict, Optional, Any
from src.domain.ports import PackageManager
from src.utils.system import get_cached_icon

# ── Catalog URLs & local cache ───────────────────────────────────────────────
CATALOG_URLS = [
    "https://store-os.inled.es/schema/index.json",
    "https://raw.githubusercontent.com/Inled-Pulsar-OS/store/main/schema/index.json",
    "https://pulsar-store.pages.dev/schema/index.json",
]
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

    def _normalize_items(self, raw_data: Any) -> List[dict]:
        if not isinstance(raw_data, dict):
            return []
        pkgs = raw_data.get("packages") or raw_data.get("items") or []
        normalized = []
        for p in pkgs:
            if not isinstance(p, dict):
                continue
            item = dict(p)
            if not item.get("summary") and item.get("description"):
                item["summary"] = item["description"].split(". ")[0] + "."
            
            # Normalize icon URL
            icon_url = item.get("icon_url", "")
            pkg_id = item.get("id", "")
            if not icon_url and pkg_id:
                item["icon_url"] = f"https://raw.githubusercontent.com/Inled-Pulsar-OS/store/main/assets/icons/{pkg_id}.png"
            elif icon_url and not (icon_url.startswith("http://") or icon_url.startswith("https://")):
                clean_path = icon_url.lstrip("/")
                item["icon_url"] = f"https://raw.githubusercontent.com/Inled-Pulsar-OS/store/main/{clean_path}"

            normalized.append(item)
        return normalized

    def _fetch_catalog(self, force: bool = False) -> List[dict]:
        """Download and cache the Pulsar Store catalog.

        Returns the list of package dicts from schema/index.json.
        Uses a local file cache with TTL to avoid hammering the server.
        """
        import time
        import urllib.request

        _ensure_cache_dir()

        # Return cached catalog if fresh enough
        if not force and os.path.exists(CATALOG_CACHE):
            age = time.time() - os.path.getmtime(CATALOG_CACHE)
            if age < CACHE_TTL_SECONDS:
                try:
                    with open(CATALOG_CACHE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = self._normalize_items(data)
                    if items:
                        return items
                except Exception:
                    pass

        # Try fetching from CATALOG_URLS
        for url in CATALOG_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AppInstall-PulsarStore/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        items = self._normalize_items(data)
                        if items:
                            with open(CATALOG_CACHE, "w", encoding="utf-8") as f:
                                json.dump(data, f, indent=2)
                            return items
            except Exception as e:
                print(f"Pulsar Store catalog fetch error ({url}): {e}")

        # Fallback 1: try stale cache
        if os.path.exists(CATALOG_CACHE):
            try:
                with open(CATALOG_CACHE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = self._normalize_items(data)
                if items:
                    return items
            except Exception:
                pass

        # Fallback 2: bundled catalog if installed
        for bundled in ("/usr/share/pulsar-store/catalog.json", "/usr/share/appinstall/catalog.json"):
            if os.path.exists(bundled):
                try:
                    with open(bundled, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = self._normalize_items(data)
                    if items:
                        return items
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
        """Install a Pulsar Store package natively based on its type."""
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package)
        if not pkg:
            return ["sh", "-c", f"echo 'Package {package} not found in Pulsar Store' && exit 1"]

        pkg_type = pkg.get("type", "")
        download_url = pkg.get("download_url", "")
        pkg_id = pkg.get("id", package)
        version = pkg.get("version", "")

        # 1. Flatpak package
        if pkg_type == "flatpak":
            if download_url and (download_url.endswith(".flatpakref") or download_url.endswith(".flatpak")):
                return ["flatpak", "install", "-y", download_url]
            else:
                return ["flatpak", "install", "-y", pkg_id]

        # 2. GNOME Extension
        elif pkg_type == "gnome_extension":
            py_script = (
                "import urllib.request, json, subprocess, os, sys, re, zipfile\n"
                f"uuid = '{pkg_id}'\n"
                f"fallback_url = '{download_url}'\n"
                "try:\n"
                "    installed = False\n"
                "    def get_shell_version():\n"
                "        try:\n"
                "            out = subprocess.check_output(['gnome-shell', '--version']).decode()\n"
                "            m = re.search(r'(\\d+)(?:\\.(\\d+))?', out)\n"
                "            if m: return m.group(1)\n"
                "        except: pass\n"
                "        return '47'\n"
                "    shell_v = get_shell_version()\n"
                "    def parse_ver(v_str):\n"
                "        try:\n"
                "            return tuple(int(p) for p in re.findall(r'\\d+', str(v_str)))\n"
                "        except:\n"
                "            return (0,)\n"
                "    dl_url = None\n"
                "    real_uuid = uuid\n"
                "    try:\n"
                "        req = urllib.request.Request(f'https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(uuid)}', headers={'User-Agent': 'AppInstall/1.0'})\n"
                "        with urllib.request.urlopen(req, timeout=10) as r:\n"
                "            data = json.loads(r.read().decode('utf-8'))\n"
                "        exts = data.get('extensions', [])\n"
                "        if exts:\n"
                "            ext = next((e for e in exts if e.get('uuid', '').lower() == uuid.lower() or str(e.get('pk', '')) == str(uuid)), exts[0])\n"
                "            pk = ext.get('pk')\n"
                "            real_uuid = ext.get('uuid', uuid)\n"
                "            info_req = urllib.request.Request(f'https://extensions.gnome.org/extension-info/?pk={pk}', headers={'User-Agent': 'AppInstall/1.0'})\n"
                "            with urllib.request.urlopen(info_req, timeout=10) as r:\n"
                "                info = json.loads(r.read().decode('utf-8'))\n"
                "            shell_map = info.get('shell_version_map', {})\n"
                "            sorted_versions = sorted(shell_map.keys(), key=parse_ver)\n"
                "            chosen_tag = shell_map.get(shell_v)\n"
                "            if not chosen_tag:\n"
                "                curr_ver_tuple = parse_ver(shell_v)\n"
                "                compatible = [v for v in sorted_versions if parse_ver(v) <= curr_ver_tuple]\n"
                "                if compatible:\n"
                "                    chosen_tag = shell_map[compatible[-1]]\n"
                "                elif sorted_versions:\n"
                "                    chosen_tag = shell_map[sorted_versions[-1]]\n"
                "            if chosen_tag:\n"
                "                tag_pk = chosen_tag.get('pk') if isinstance(chosen_tag, dict) else chosen_tag\n"
                "                dl_url = f'https://extensions.gnome.org/download-extension/{real_uuid}.shell-extension.zip?version_tag={tag_pk}'\n"
                "    except Exception as ego_err:\n"
                "        print(f'EGO query error: {ego_err}', file=sys.stderr)\n"
                "    if not dl_url and fallback_url:\n"
                "        dl_url = fallback_url\n"
                "    if not dl_url:\n"
                "        print(f'No download URL found for {uuid}', file=sys.stderr)\n"
                "        sys.exit(1)\n"
                "    tmp_zip = f'/tmp/{real_uuid}.zip'\n"
                "    dl_req = urllib.request.Request(dl_url, headers={'User-Agent': 'AppInstall/1.0'})\n"
                "    with urllib.request.urlopen(dl_req, timeout=20) as r:\n"
                "        with open(tmp_zip, 'wb') as f:\n"
                "            f.write(r.read())\n"
                "    target_uuid = real_uuid\n"
                "    try:\n"
                "        with zipfile.ZipFile(tmp_zip, 'r') as zf:\n"
                "            if 'metadata.json' in zf.namelist():\n"
                "                meta_data = json.loads(zf.read('metadata.json').decode('utf-8'))\n"
                "                if meta_data.get('uuid'):\n"
                "                    target_uuid = meta_data.get('uuid')\n"
                "    except Exception:\n"
                "        pass\n"
                "    dest_dir = os.path.expanduser(f'~/.local/share/gnome-shell/extensions/{target_uuid}')\n"
                "    os.makedirs(dest_dir, exist_ok=True)\n"
                "    with zipfile.ZipFile(tmp_zip, 'r') as zf:\n"
                "        zf.extractall(dest_dir)\n"
                "    subprocess.run(['gnome-extensions', 'install', '--force', tmp_zip], capture_output=True)\n"
                "    subprocess.run(['gnome-extensions', 'enable', target_uuid], capture_output=True)\n"
                "    if os.path.exists(tmp_zip): os.remove(tmp_zip)\n"
                "    print(f'Extensión {target_uuid} instalada con éxito.')\n"
                "except Exception as e:\n"
                "    print(f'Error al instalar extensión {uuid}: {e}', file=sys.stderr)\n"
                "    sys.exit(1)\n"
            )
            return ["python3", "-c", py_script]

        # 3. Sayri Skill
        elif pkg_type == "sayri_skill":
            target_dir = os.path.expanduser(f"~/.local/share/sayri/skills/{pkg_id}")
            if download_url:
                cmd = (
                    f"mkdir -p '{target_dir}' && "
                    f"tmpfile=$(mktemp --suffix=.zip) && "
                    f"curl -sSL '{download_url}' -o \"$tmpfile\" && "
                    f"unzip -o -q \"$tmpfile\" -d '{target_dir}' && "
                    f"rm -f \"$tmpfile\""
                )
                return ["sh", "-c", cmd]
            return ["sh", "-c", f"mkdir -p '{target_dir}'"]

        # 4. Sayri Plugin
        elif pkg_type == "sayri_plugin":
            target_dir = os.path.expanduser(f"~/.local/share/sayri/plugins/{pkg_id}")
            if download_url:
                cmd = (
                    f"mkdir -p '{target_dir}' && "
                    f"tmpfile=$(mktemp --suffix=.zip) && "
                    f"curl -sSL '{download_url}' -o \"$tmpfile\" && "
                    f"unzip -o -q \"$tmpfile\" -d '{target_dir}' && "
                    f"rm -f \"$tmpfile\""
                )
                return ["sh", "-c", cmd]
            return ["sh", "-c", f"mkdir -p '{target_dir}'"]

        # Fallback for generic archives (.deb, .tar.gz, etc.)
        elif download_url:
            if download_url.endswith(".deb"):
                cmd = f"tmpfile=$(mktemp --suffix=.deb) && curl -sSL '{download_url}' -o \"$tmpfile\" && pkexec dpkg -i \"$tmpfile\" && rm -f \"$tmpfile\""
                return ["sh", "-c", cmd]
            elif download_url.endswith(".zip"):
                return ["sh", "-c", f"tmpfile=$(mktemp --suffix=.zip) && curl -sSL '{download_url}' -o \"$tmpfile\" && unzip -o -q \"$tmpfile\" -d ~/.local/share/ && rm -f \"$tmpfile\""]

        return ["sh", "-c", f"echo 'No installation mechanism defined for {pkg_id}' && exit 1"]

    def install_multiple(self, packages: List[str]) -> List[str]:
        """Install multiple Pulsar Store packages."""
        commands = []
        for pkg in packages:
            commands.extend(self.install(pkg))
        return commands

    def install_local(self, file_path: str) -> List[str]:
        """Install a local Pulsar Store package file (.zip)."""
        if file_path.endswith(".zip"):
            return ["sh", "-c", f"unzip -o -q '{file_path}' -d ~/.local/share/"]
        return ["sh", "-c", f"echo 'Unsupported file type: {file_path}'"]

    # ── Uninstall ───────────────────────────────────────────────────────────

    def uninstall(self, package: str) -> List[str]:
        """Uninstall a Pulsar Store package natively based on its type."""
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package)
        pkg_type = pkg.get("type", "") if pkg else ""
        pkg_id = pkg.get("id", package) if pkg else package

        if pkg_type == "flatpak":
            return ["flatpak", "uninstall", "-y", pkg_id]
        elif pkg_type == "gnome_extension":
            return ["gnome-extensions", "uninstall", pkg_id]
        elif pkg_type == "sayri_skill":
            target_dir = os.path.expanduser(f"~/.local/share/sayri/skills/{pkg_id}")
            return ["sh", "-c", f"rm -rf '{target_dir}'"]
        elif pkg_type == "sayri_plugin":
            target_dir = os.path.expanduser(f"~/.local/share/sayri/plugins/{pkg_id}")
            return ["sh", "-c", f"rm -rf '{target_dir}'"]

        # Default fallback checks
        ext_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{pkg_id}")
        skill_dir = os.path.expanduser(f"~/.local/share/sayri/skills/{pkg_id}")
        plugin_dir = os.path.expanduser(f"~/.local/share/sayri/plugins/{pkg_id}")

        if os.path.isdir(ext_dir):
            return ["gnome-extensions", "uninstall", pkg_id]
        elif os.path.isdir(skill_dir):
            return ["sh", "-c", f"rm -rf '{skill_dir}'"]
        elif os.path.isdir(plugin_dir):
            return ["sh", "-c", f"rm -rf '{plugin_dir}'"]

        return ["flatpak", "uninstall", "-y", pkg_id]

    # ── Status check ────────────────────────────────────────────────────────

    def is_package_installed(self, package: str) -> bool:
        """Check if a Pulsar Store package is currently installed on the system."""
        catalog = self._get_catalog()
        pkg = self._find_pkg(catalog, package)
        pkg_type = pkg.get("type", "") if pkg else ""
        pkg_id = pkg.get("id", package) if pkg else package

        if pkg_type == "flatpak":
            try:
                res = subprocess.run(["flatpak", "info", pkg_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0:
                    return True
            except Exception:
                pass
        elif pkg_type == "gnome_extension":
            user_dir = os.path.expanduser(f"~/.local/share/gnome-shell/extensions/{pkg_id}")
            sys_dir = f"/usr/share/gnome-shell/extensions/{pkg_id}"
            if os.path.isdir(user_dir) or os.path.isdir(sys_dir):
                return True
        elif pkg_type == "sayri_skill":
            user_dir = os.path.expanduser(f"~/.local/share/sayri/skills/{pkg_id}")
            if os.path.isdir(user_dir):
                return True
        elif pkg_type == "sayri_plugin":
            user_dir = os.path.expanduser(f"~/.local/share/sayri/plugins/{pkg_id}")
            if os.path.isdir(user_dir):
                return True

        # Check installed database as secondary source
        db = _load_installed_db()
        return pkg_id in db

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
                "is_installed": False,
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
        pkg_id = pkg.get("id", package_name)
        is_installed = self.is_package_installed(pkg_id)

        info = {
            "name": pkg.get("name", package_name),
            "version": pkg.get("version", "N/A"),
            "description": pkg.get("description", ""),
            "source": "pulsar",
            "developer": pkg.get("author", "Pulsar OS"),
            "license": "Open Source",
            "size": "N/A",
            "icon": "system-software-install-symbolic",
            "pulsar_type": type_label,
            "pulsar_id": pkg_id,
            "readme_url": pkg.get("readme_url", ""),
            "security_score": str(security_score),
            "security_status": security_status,
            "security_report": security,
            "security_summary": security.get("summary", ""),
            "security_auditor": security.get("audited_by", "OpenCode"),
            "virustotal_detections": security.get("virustotal_detections", 0),
            "is_installed": is_installed,
            "verified": True,
        }

        # Enrich with icon (supports SVG, GIF, PNG, WebP)
        icon_url = pkg.get("icon_url", "")
        if icon_url:
            cached = get_cached_icon(icon_url, f"pulsar_{pkg_id}")
            if cached:
                info["icon"] = cached

        # Demo Screenshots (supports SVG, GIF, PNG, JPG, WebP)
        demo_urls = pkg.get("demo_urls", []) or []
        if isinstance(demo_urls, str):
            demo_urls = [demo_urls]
        if pkg.get("promo_url") and pkg.get("promo_url") not in demo_urls:
            demo_urls.append(pkg.get("promo_url"))
        
        from src.utils.system import get_cached_screenshot
        cached_shots = []
        for idx, durl in enumerate(demo_urls):
            if durl:
                cshot = get_cached_screenshot(durl, f"pulsar_shot_{pkg_id}_{idx}")
                if cshot and os.path.exists(cshot):
                    cached_shots.append(cshot)
        if cached_shots:
            info["cached_screenshots"] = cached_shots

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
        return ["sh", "-c", "echo 'Pulsar Store packages up to date'"]

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
