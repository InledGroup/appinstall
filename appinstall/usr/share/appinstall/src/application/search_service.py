import os
import json
import concurrent.futures
from typing import List, Dict
from src.domain.ports import PackageManager
from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
from src.infrastructure.adapters.snap_adapter import SnapAdapter
from src.infrastructure.adapters.aur_adapter import AurAdapter

CONFIG_PATH = os.path.expanduser("~/.config/appinstall/config.json")

class SearchService:
    def __init__(self, system_pm: PackageManager):
        self.system_pm = system_pm
        self.flatpak_adapter = FlatpakAdapter()
        self.snap_adapter = SnapAdapter()
        self.aur_adapter = AurAdapter()
        self.priority_order = self.load_priority_order()

    def load_priority_order(self) -> List[str]:
        default_order = ["system", "flatpak", "snap", "aur"]
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
            with open(CONFIG_PATH, 'w') as f:
                json.dump({"search_priority": order}, f)
        except Exception as e:
            print(f"Error saving priority configuration: {e}")

    def search(self, query: str) -> List[Dict[str, str]]:
        """Busca paquetes de forma concurrente en todas las fuentes disponibles."""
        if not query or len(query) < 3:
            return []
            
        results = []
        
        # Lista de tareas a ejecutar en paralelo
        tasks = []
        
        # 1. System Package Manager (APT/DNF/Pacman) siempre disponible
        tasks.append(("system", lambda: self.system_pm.search(query)))
        
        # 2. Flatpak (si está disponible)
        if self.flatpak_adapter.is_available():
            tasks.append(("flatpak", lambda: self.flatpak_adapter.search(query)))
            
        # 3. Snap (si está disponible)
        if self.snap_adapter.is_available():
            tasks.append(("snap", lambda: self.snap_adapter.search(query)))
            
        # 4. AUR (si estamos en Arch Linux)
        if self.aur_adapter.is_available():
            tasks.append(("aur", lambda: self.aur_adapter.search(query)))
            
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

    def get_popular_apps(self, limit=12) -> List[Dict[str, str]]:
        if self.flatpak_adapter.is_available():
            return self.flatpak_adapter.get_popular(limit)
        return []

    def get_trending_apps(self, limit=12) -> List[Dict[str, str]]:
        if self.flatpak_adapter.is_available():
            return self.flatpak_adapter.get_trending(limit)
        return []
