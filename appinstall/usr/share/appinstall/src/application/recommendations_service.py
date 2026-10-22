# English: Curated recommendations shown on the home screen, driven by a JSON file
#          published in the repository so the maintainer can edit sections freely.
# Español: Recomendaciones curadas que se muestran en el inicio, dirigidas por un
#          archivo JSON publicado en el repositorio para que el mantenedor pueda
#          editar las secciones libremente.

import json
import os
import urllib.parse
import urllib.request

# Icono por defecto del catálogo de Pulsar Store (mismo patrón que usa el
# adaptador cuando un paquete no trae icono propio)
PULSAR_ICON_URL = "https://raw.githubusercontent.com/Inled-Pulsar-OS/store/main/assets/icons/{}.png"

# Caché local de iconos de extensiones de extensions.gnome.org
EGO_ICON_CACHE = os.path.expanduser("~/.cache/appinstall/ego_icons.json")

# Pulsar OS and derivatives: everything that can appear is filtered by what the
# host actually has installed, so a section never shows an uninstallable app.
MANAGER_BY_SOURCE = {
    "flatpak": "flatpak",
    "snap": "snap",
    "apt": "apt",
    "pacman": "pacman",
    "aur": "pacman",
    "dnf": "dnf",
    "pulsar": None,      # Pulsar Store catalogue is always available
    "gnome-extension": None,
}

# distro IDs that imply the AUR is usable
_AUR_DISTROS = {"arch", "artix", "endeavouros", "manjaro", "cachyos", "garuda",
                "arcolinux", "steamos", "pops"}


def _os_release():
    info = {"id": "", "id_like": ""}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    value = value.strip().strip('"').strip("'").lower()
                    if key == "ID":
                        info["id"] = value
                    elif key == "ID_LIKE":
                        info["id_like"] = value
            break
        except OSError:
            continue
    return info


class RecommendationsService:
    """Loads and filters the curated recommendations file."""

    def __init__(self):
        self._os = _os_release()
        self._tools = None

    # ── Location ────────────────────────────────────────────────────────────

    @staticmethod
    def _candidates():
        here = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(os.path.dirname(here))  # src/application -> repo
        yield os.environ.get("APPINSTALL_RECOMMENDATIONS", "")
        yield os.path.expanduser("~/.config/appinstall/recommendations.json")
        yield os.path.join(repo_root, "recommendations.json")
        yield os.path.join(here, "recommendations.json")
        yield "/usr/share/appinstall/recommendations.json"
        yield "/usr/local/share/appinstall/recommendations.json"

    def find_file(self):
        for candidate in self._candidates():
            if candidate and os.path.isfile(candidate):
                return candidate
        return None

    # ── Host capabilities ───────────────────────────────────────────────────

    def _has(self, tool):
        if self._tools is None:
            from shutil import which
            self._tools = {t: bool(which(t)) for t in
                           ("flatpak", "snap", "apt", "pacman", "dnf", "gnome-shell")}
        return self._tools.get(tool, False)

    def _is_gnome(self):
        desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or ""
                   + os.environ.get("DESKTOP_SESSION") or "").lower()
        return "gnome" in desktop or self._has("gnome-shell")

    def _distros_of_host(self):
        return {self._os.get("id", "")} | set(self._os.get("id_like", "").split())

    def source_available(self, source):
        """True when this host can actually install packages from `source`."""
        source = (source or "").strip().lower()
        if source == "aur":
            return self._has("pacman") and bool(_AUR_DISTROS & self._distros_of_host())
        if source == "gnome-extension":
            return self._is_gnome()
        manager = MANAGER_BY_SOURCE.get(source)
        if manager is None:
            return source in MANAGER_BY_SOURCE  # unknown sources are skipped
        return self._has(manager)

    def distro_allowed(self, allowed):
        """`allowed` is a list of distro IDs (or ["any"]) from the JSON."""
        if not allowed or "any" in [str(d).lower() for d in allowed]:
            return True
        host = self._distros_of_host()
        return bool(host & {str(d).lower() for d in allowed})

    def app_visible(self, app):
        if not isinstance(app, dict) or not app.get("name"):
            return False
        if not self.source_available(app.get("source", "flatpak")):
            return False
        return self.distro_allowed(app.get("distros"))

    # ── Loading ─────────────────────────────────────────────────────────────

    # ── Icons ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_ego_icon_cache():
        try:
            with open(EGO_ICON_CACHE, encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save_ego_icon_cache(data):
        try:
            os.makedirs(os.path.dirname(EGO_ICON_CACHE), exist_ok=True)
            with open(EGO_ICON_CACHE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _ego_icon_url(self, uuid, cache):
        """Icono de una extensión GNOME desde extensions.gnome.org (con caché)."""
        cached = cache.get(uuid)
        if cached:
            return cached
        # Los fallos previos no se cachean como definitivos: se reintentan
        url = ""
        try:
            query = urllib.parse.quote(uuid)
            req = urllib.request.Request(
                f"https://extensions.gnome.org/extension-query/?search={query}",
                headers={"User-Agent": "AppInstall/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for ext in data.get("extensions", []):
                if ext.get("uuid") == uuid:
                    # Mismo criterio que el resto de la app: se ignora el icon
                    # genérico plugin.png de extensions.gnome.org
                    icon = ext.get("icon") or ""
                    if icon and not icon.endswith("plugin.png"):
                        if icon.startswith("/"):
                            icon = "https://extensions.gnome.org" + icon
                        url = icon
                    break
        except Exception:
            url = ""
        cache[uuid] = url
        return url

    def enrich_icons(self, sections):
        """English: Fill in the icon of every app that does not declare one,
        using the same sources the app already uses (Pulsar Store catalogue
        and extensions.gnome.org), with a local cache so it is done once.
        Español: Completa el icono de cada app que no lleve uno declarado,
        usando las mismas fuentes que ya usa la aplicación, con caché local.
        """
        ego_cache = self._load_ego_icon_cache()
        ego_dirty = False

        for section in sections:
            for app in section.get("apps", []):
                if app.get("icon"):
                    continue
                source = str(app.get("source", "")).lower()
                name = str(app.get("name", ""))
                if source == "pulsar":
                    app["icon"] = PULSAR_ICON_URL.format(name)
                elif source == "gnome-extension" and name:
                    icon = self._ego_icon_url(name, ego_cache)
                    ego_dirty = True
                    if icon:
                        app["icon"] = icon

        if ego_dirty:
            self._save_ego_icon_cache(ego_cache)
        return sections

    def load_sections(self):
        """Returns a list of {"title", "desc", "apps"} with visible apps only."""
        path = self.find_file()
        if not path:
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return []

        raw = data.get("sections") if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return []

        sections = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            apps = [a for a in entry.get("apps", []) if self.app_visible(a)]
            if not apps:
                continue
            sections.append({
                "title": str(entry.get("title") or _("Recomendados")),
                "desc": str(entry.get("desc") or entry.get("description") or ""),
                "apps": apps,
            })
        return self.enrich_icons(sections)

    def load_app(self, name, source):
        """Finds a single curated app (used as a fallback by the search)."""
        name = (name or "").strip()
        source = (source or "").strip().lower()
        for section in self.load_sections():
            for app in section["apps"]:
                if app.get("name") == name and (
                        not source or str(app.get("source", "")).lower() == source):
                    return app
        return None
