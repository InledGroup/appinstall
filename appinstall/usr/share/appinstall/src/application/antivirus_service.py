import os
import subprocess
import threading
from gi.repository import GLib

class AntivirusService:
    def __init__(self, package_manager):
        self.package_manager = package_manager

    def check_clamav_status(self, on_complete):
        def _run():
            try:
                result = subprocess.run(['which', 'clamscan'], 
                                      capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    version_result = subprocess.run(['clamscan', '--version'], 
                                                  capture_output=True, text=True, timeout=10)
                    if version_result.returncode == 0:
                        version = version_result.stdout.strip()
                        GLib.idle_add(on_complete, True, version)
                    else:
                        GLib.idle_add(on_complete, False, None)
                else:
                    GLib.idle_add(on_complete, False, None)
            except Exception as e:
                print(f"Error verificando ClamAV: {e}")
                GLib.idle_add(on_complete, False, None)

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

    def install_clamav(self, on_progress, on_status, on_complete):
        def _run():
            try:
                # Corregir dependencias rotas
                GLib.idle_add(on_status, "Corrigiendo dependencias...")
                fix_process = subprocess.Popen(self.package_manager.fix_broken(),
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                while True:
                    output = fix_process.stdout.readline()
                    if output == '' and fix_process.poll() is not None:
                        break
                    if output:
                        GLib.idle_add(on_progress)
                fix_process.communicate()
                
                # Actualizar repositorios
                GLib.idle_add(on_status, "Actualizando repositorios...")
                update_process = subprocess.Popen(self.package_manager.update_cache(),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                update_process.communicate()
                
                # Instalar ClamAV
                GLib.idle_add(on_status, "Instalando ClamAV...")
                install_process = subprocess.Popen(self.package_manager.install_clamav(),
                                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                while True:
                    output = install_process.stdout.readline()
                    if output == '' and install_process.poll() is not None:
                        break
                    if output:
                        GLib.idle_add(on_progress)
                
                _, stderr = install_process.communicate()
                
                if install_process.returncode == 0:
                    GLib.idle_add(on_complete, True, None)
                else:
                    # Reintento con autoremove
                    GLib.idle_add(on_status, "Reintentando instalación...")
                    subprocess.run(self.package_manager.autoremove(), capture_output=True, timeout=120)
                    
                    retry_process = subprocess.Popen(self.package_manager.install_clamav(),
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                    while True:
                        output = retry_process.stdout.readline()
                        if output == '' and retry_process.poll() is not None:
                            break
                        if output:
                            GLib.idle_add(on_progress)
                    _, retry_stderr = retry_process.communicate()
                    
                    if retry_process.returncode == 0:
                        GLib.idle_add(on_complete, True, None)
                    else:
                        GLib.idle_add(on_complete, False, f"Error original: {stderr}\nError reintento: {retry_stderr}")
            except Exception as e:
                GLib.idle_add(on_complete, False, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

    def update_definitions(self, on_progress, on_complete):
        def _run():
            try:
                process = subprocess.Popen(['pkexec', 'freshclam'],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        GLib.idle_add(on_progress)
                
                _, stderr = process.communicate()
                
                if process.returncode == 0:
                    GLib.idle_add(on_complete, True, None)
                else:
                    GLib.idle_add(on_complete, False, stderr)
            except Exception as e:
                GLib.idle_add(on_complete, False, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()

    def run_scan(self, scan_paths, deep_scan, on_progress, on_result, on_complete):
        def _run():
            try:
                cmd = ['clamscan', '-r', '--no-summary']
                if deep_scan:
                    cmd.extend(['--scan-archive', '--heuristic-scan-precedence'])
                cmd.extend(scan_paths)
                
                GLib.idle_add(on_result, f"Ejecutando: {' '.join(cmd)}\n\n")
                
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                         stderr=subprocess.PIPE, universal_newlines=True)
                
                infected_files = []
                scanned_files = 0
                
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        line = output.strip()
                        scanned_files += 1
                        
                        if scanned_files % 100 == 0:
                            GLib.idle_add(on_progress)
                        
                        if "FOUND" in line:
                            infected_files.append(line)
                            GLib.idle_add(on_result, f"🦠 INFECTADO: {line}\n")
                        elif scanned_files % 1000 == 0:
                            GLib.idle_add(on_result, f"Analizados: {scanned_files} archivos...\n")
                
                _, stderr = process.communicate()
                GLib.idle_add(on_complete, True, len(infected_files), scanned_files, stderr)
            except Exception as e:
                GLib.idle_add(on_complete, False, 0, 0, str(e))

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
