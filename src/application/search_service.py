import os
import json
import concurrent.futures
from typing import List, Dict
from src.domain.ports import PackageManager
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter
from src.infrastructure.adapters.brew_adapter import BrewAdapter
from src.infrastructure.adapters.pulsar_store_adapter import PulsarStoreAdapter

CONFIG_PATH = os.path.expanduser("~/.config/appinstall/config.json")

class SearchService:
    def __init__(self, system_pm: PackageManager):
        self.system_pm = system_pm
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()
        self.brew_adapter = BrewAdapter()
        self.pulsar_adapter = PulsarStoreAdapter()
        self.priority_order = self.load_priority_order()

    def load_priority_order(self) -> List[str]:
        default_order = ["pulsar", "system", "flatpak", "snap", "aur", "brew"]
        if not os.path.exists(CONFIG_PATH):
            return default_order
        try:
            with open(CONFIG_PATH, 'r') as f:
                data = json.load(f)
                return data.get("search_priority", default_order)
        except:
            return default_order

    def save_priority_order(self, order: List[str]):
        self.priority_order = order
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            data = {}
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, 'r') as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data["search_priority"] = order
            with open(CONFIG_PATH, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving priority configuration: {e}")

    def search(self, query: str) -> List[Dict[str, str]]:
        """Busca paquetes de forma concurrente en todas las fuentes disponibles."""
        if not query or len(query) < 3:
            return []
            
        results = []
        
        # Lista de tareas a ejecutar en paralelo
        tasks = []

        # 1. Pulsar Store
        if self.pulsar_adapter.is_available():
            tasks.append(("pulsar", lambda: self.pulsar_adapter.search(query)))
        
        # 2. System Package Manager (APT/DNF/Pacman)
        tasks.append(("system", lambda: self.system_pm.search(query)))
        
        # 3. Flatpak (si está disponible)
        if self.flatpak_adapter.is_available():
            tasks.append(("flatpak", lambda: self.flatpak_adapter.search(query)))
            
        # 4. Snap (si está disponible)
        if self.snap_adapter.is_available():
            tasks.append(("snap", lambda: self.snap_adapter.search(query)))
            
        # 5. AUR (si estamos en Arch Linux)
        if self.aur_adapter.is_available():
            tasks.append(("aur", lambda: self.aur_adapter.search(query)))
            
        # 6. Homebrew (si está disponible)
        if self.brew_adapter.is_available():
            tasks.append(("brew", lambda: self.brew_adapter.search(query)))

        # 7. GNOME Extensions (si el entorno es GNOME)
        from src.utils.system import is_gnome_desktop
        if is_gnome_desktop():
            tasks.append(("gnome-extension", lambda: self._search_gnome_extensions(query)))
            
        # Ejecutar búsquedas en paralelo con ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_source = {executor.submit(fn): source for source, fn in tasks}
            for future in concurrent.futures.as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    source_results = future.result()
                    if source_results:
                        # Limitar resultados por fuente para mantener la UI limpia (máx. 10 por fuente)
                        results.extend(source_results[:10])
                except Exception as e:
                    print(f"Error in search task for source '{source}': {e}")
                    
        # Ordenar resultados de acuerdo con la prioridad del usuario
        def get_sort_key(res):
            res_source = res.get('source', 'system')
            # Mapear gestores nativos a 'system'
            if res_source in ['apt', 'dnf', 'pacman']:
                res_source = 'system'
            try:
                return self.priority_order.index(res_source)
            except ValueError:
                return len(self.priority_order)
                
        results.sort(key=get_sort_key)
        return results

    def _search_gnome_extensions(self, query: str) -> List[Dict[str, str]]:
        import urllib.request
        import urllib.parse
        from src.utils.system import get_cached_icon
        
        results = []
        try:
            url = f"https://extensions.gnome.org/extension-query/?search={urllib.parse.quote(query)}&n_per_page=8"
            req = urllib.request.Request(url, headers={"User-Agent": "AppInstall/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                for ext in data.get("extensions", []):
                    uuid = ext.get("uuid", "")
                    icon_rel = ext.get("icon", "")
                    icon_path = ""
                    if icon_rel and not icon_rel.endswith("plugin.png"):
                        full_icon_url = f"https://extensions.gnome.org{icon_rel}" if icon_rel.startswith("/") else icon_rel
                        icon_path = get_cached_icon(full_icon_url, f"ego_{ext.get('pk', '0')}")
                    
                    results.append({
                        "name": uuid,
                        "display_name": ext.get("name", uuid),
                        "desc": ext.get("description", ""),
                        "source": "gnome-extension",
                        "icon": icon_path if icon_path else "application-x-addon-symbolic",
                        "ego_pk": ext.get("pk"),
                        "uuid": uuid,
                        "version": ext.get("version", "")
                    })
        except Exception as e:
            print(f"Error querying GNOME extensions in SearchService: {e}")
        return results

    def get_pulsar_store_highlights(self, limit=6) -> List[Dict[str, str]]:
        catalog = self.pulsar_adapter._get_catalog()
        highlights = []
        for pkg in catalog[:limit]:
            pkg_id = pkg.get("id", "")
            icon_url = pkg.get("icon_url", "")
            from src.utils.system import get_cached_icon
            icon_path = get_cached_icon(icon_url, f"pulsar_{pkg_id}") if icon_url else ""
            highlights.append({
                "name": pkg_id,
                "display_name": pkg.get("name", pkg_id),
                "desc": pkg.get("summary") or pkg.get("description", ""),
                "source": "pulsar",
                "icon": icon_path if icon_path else "system-software-install-symbolic",
                "version": pkg.get("version", "1.0"),
                "type": pkg.get("type", "")
            })
        return highlights

    def get_gnome_extensions_highlights(self, limit=6) -> List[Dict[str, str]]:
        import urllib.request
        from src.utils.system import get_cached_icon
        results = []
        try:
            url = f"https://extensions.gnome.org/extension-query/?sort=downloads&n_per_page={limit}"
            req = urllib.request.Request(url, headers={"User-Agent": "AppInstall/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                for ext in data.get("extensions", []):
                    uuid = ext.get("uuid", "")
                    icon_rel = ext.get("icon", "")
                    icon_path = ""
                    if icon_rel and not icon_rel.endswith("plugin.png"):
                        full_icon_url = f"https://extensions.gnome.org{icon_rel}" if icon_rel.startswith("/") else icon_rel
                        icon_path = get_cached_icon(full_icon_url, f"ego_{ext.get('pk', '0')}")
                    results.append({
                        "name": uuid,
                        "display_name": ext.get("name", uuid),
                        "desc": ext.get("description", ""),
                        "source": "gnome-extension",
                        "icon": icon_path if icon_path else "application-x-addon-symbolic",
                        "ego_pk": ext.get("pk"),
                        "uuid": uuid
                    })
        except Exception as e:
            print(f"Error fetching GNOME extensions highlights: {e}")
        return results

    def get_popular_apps(self, limit=12) -> List[Dict[str, str]]:
        if self.flatpak_adapter.is_available():
            return self.flatpak_adapter.get_popular(limit)
        return []

    def get_trending_apps(self, limit=12) -> List[Dict[str, str]]:
        if self.flatpak_adapter.is_available():
            return self.flatpak_adapter.get_trending(limit)
        return []
