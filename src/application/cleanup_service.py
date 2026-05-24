import os
import shutil
import subprocess
import threading
from gi.repository import GLib

class CleanupService:
    def __init__(self, package_manager):
        self.package_manager = package_manager

    def get_directory_size(self, directory):
        """Calcula el tamaño de un directorio."""
        total_size = 0
        try:
            # Expandir ~ y variables
            expanded_dir = os.path.expanduser(directory)
            
            if "*" in expanded_dir:
                # Manejar wildcards
                import glob
                matching_dirs = glob.glob(expanded_dir)
                for match_dir in matching_dirs:
                    if os.path.exists(match_dir):
                        total_size += self._calculate_dir_size(match_dir)
            else:
                if os.path.exists(expanded_dir):
                    total_size = self._calculate_dir_size(expanded_dir)
        except Exception as e:
            print(f"Error calculando tamaño de {directory}: {e}")
        
        return total_size

    def _calculate_dir_size(self, directory):
        """Calcula el tamaño de un directorio específico."""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        pass  # Archivo inaccesible
        except Exception:
            pass
        
        return total_size

    def get_orphan_packages_size(self):
        """Estima el tamaño de los paquetes huérfanos."""
        try:
            packages = self.package_manager.list_installed()
            return len(packages) * 1024 * 1024  # 1MB promedio estimado
        except:
            return 0

    def get_package_cache_size(self):
        """Calcula el tamaño del caché de paquetes."""
        return self._calculate_dir_size(self.package_manager.get_cache_directory())

    def clean_directory(self, directory):
        """Limpia un directorio específico."""
        cleaned_size = 0
        try:
            expanded_dir = os.path.expanduser(directory)
            
            if "*" in expanded_dir:
                import glob
                matching_dirs = glob.glob(expanded_dir)
                for match_dir in matching_dirs:
                    if os.path.exists(match_dir):
                        if os.path.isfile(match_dir):
                            size = os.path.getsize(match_dir)
                            os.remove(match_dir)
                            cleaned_size += size
                        elif os.path.isdir(match_dir):
                            size = self._calculate_dir_size(match_dir)
                            shutil.rmtree(match_dir, ignore_errors=True)
                            cleaned_size += size
            else:
                if os.path.exists(expanded_dir):
                    if os.path.isfile(expanded_dir):
                        size = os.path.getsize(expanded_dir)
                        os.remove(expanded_dir)
                        cleaned_size += size
                    elif os.path.isdir(expanded_dir):
                        if directory in ["~/.cache", "/tmp", "/var/tmp", "~/.thumbnails"]:
                            for item in os.listdir(expanded_dir):
                                item_path = os.path.join(expanded_dir, item)
                                try:
                                    if os.path.isfile(item_path):
                                        size = os.path.getsize(item_path)
                                        os.remove(item_path)
                                        cleaned_size += size
                                    elif os.path.isdir(item_path):
                                        size = self._calculate_dir_size(item_path)
                                        shutil.rmtree(item_path, ignore_errors=True)
                                        cleaned_size += size
                                except:
                                    pass
                        else:
                            size = self._calculate_dir_size(expanded_dir)
                            shutil.rmtree(expanded_dir, ignore_errors=True)
                            cleaned_size += size
        except Exception as e:
            print(f"Error limpiando {directory}: {e}")
        
        return cleaned_size

    def clean_orphan_packages(self):
        """Limpia paquetes huérfanos."""
        try:
            subprocess.run(self.package_manager.autoremove(), 
                         timeout=300, capture_output=True)
        except Exception as e:
            print(f"Error limpiando paquetes huérfanos: {e}")

    def clean_package_cache(self):
        """Limpia el caché de paquetes."""
        try:
            subprocess.run(self.package_manager.clean_cache(), 
                         timeout=300, capture_output=True)
        except Exception as e:
            print(f"Error limpiando caché de paquetes: {e}")

    def run_analysis(self, selected_dirs, orphan_check, apt_check, on_progress, on_complete):
        def _run():
            try:
                analysis_results = {}
                total_size = 0
                total_ops = len(selected_dirs) + (1 if orphan_check else 0) + (1 if apt_check else 0)
                current_op = 0
                
                for directory in selected_dirs:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    size = self.get_directory_size(directory)
                    analysis_results[directory] = size
                    total_size += size
                    current_op += 1
                
                if orphan_check:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    orphan_size = self.get_orphan_packages_size()
                    analysis_results["paquetes_huerfanos"] = orphan_size
                    total_size += orphan_size
                    current_op += 1
                
                if apt_check:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    pkg_cache_size = self.get_package_cache_size()
                    analysis_results["package_cache"] = pkg_cache_size
                    total_size += pkg_cache_size
                    current_op += 1
                
                GLib.idle_add(on_complete, True, total_size, None)
            except Exception as e:
                GLib.idle_add(on_complete, False, 0, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

    def run_cleanup(self, selected_dirs, orphan_check, apt_check, on_progress, on_complete):
        def _run():
            try:
                cleaned_size = 0
                total_ops = len(selected_dirs) + (1 if orphan_check else 0) + (1 if apt_check else 0)
                current_op = 0
                
                for directory in selected_dirs:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    cleaned_size += self.clean_directory(directory)
                    current_op += 1
                
                if orphan_check:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    self.clean_orphan_packages()
                    current_op += 1
                
                if apt_check:
                    GLib.idle_add(on_progress, current_op / total_ops)
                    self.clean_package_cache()
                    current_op += 1
                
                GLib.idle_add(on_complete, True, cleaned_size, None)
            except Exception as e:
                GLib.idle_add(on_complete, False, 0, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
