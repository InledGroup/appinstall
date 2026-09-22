import os
import sys
import time
import json
import subprocess
import socket
import shutil

from src.infrastructure.services.localization import _

class DaemonService:
    """Demonio de segundo plano para comprobación y aplicación automática de actualizaciones en Pulsar OS."""

    CONFIG_PATHS = [
        os.path.expanduser("~/.config/appinstall/config.json"),
        "/etc/appinstall/config.json"
    ]

    def is_auto_update_enabled(self) -> bool:
        """Comprueba si el usuario tiene activadas las actualizaciones automáticas."""
        for path in self.CONFIG_PATHS:
            if os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if 'auto_update' in data:
                            return bool(data['auto_update'])
                except Exception as e:
                    print(f"[Daemon] Error leyendo configuración ({path}): {e}")
        # Activadas de forma predeterminada
        return True

    def check_cpu_performance(self) -> tuple[bool, str]:
        """Evalúa si el procesador del equipo tiene la potencia suficiente para compilar/actualizar en segundo plano."""
        cores = os.cpu_count() or 1
        
        # Equipos con menos de 2 núcleos no son aptos para tareas pesadas en segundo plano
        if cores < 2:
            return False, f"CPU con recursos muy limitados ({cores} núcleo/s)"

        # Comprobar información del modelo de procesador en /proc/cpuinfo
        cpu_model = ""
        low_end_keywords = [
            'atom', 'celeron', 'sempron', 'geode', 
            'pentium ii', 'pentium iii', 'pentium 4', 'pentium m',
            'core(tm)2', 'e-350', 'e-450', 'c-50', 'c-60', 'a4-', 'a6-'
        ]

        if os.path.exists('/proc/cpuinfo'):
            try:
                with open('/proc/cpuinfo', 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if line.startswith('model name'):
                            cpu_model = line.split(':', 1)[1].strip().lower()
                            break
            except Exception:
                pass

        if cpu_model:
            for kw in low_end_keywords:
                if kw in cpu_model and cores <= 2:
                    return False, f"Procesador de gama baja detectado ({cpu_model})"

        # Comprobar carga actual del sistema (evitar sobrecargar si ya está ocupado)
        try:
            load1, _, _ = os.getloadavg()
            if load1 > (cores * 1.5):
                return False, f"Carga del sistema demasiado alta ({load1:.2f} para {cores} núcleos)"
        except Exception:
            pass

        return True, f"CPU apta ({cores} núcleos: {cpu_model or 'Standard'})"

    def is_online(self) -> bool:
        """Comprueba si hay conexión a internet disponible."""
        try:
            # Conexión rápida a un DNS público
            socket.create_connection(("1.1.1.1", 53), timeout=4)
            return True
        except OSError:
            pass
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=4)
            return True
        except OSError:
            return False

    def send_notification(self, title: str, message: str, icon: str = "es.inled.AppInstall"):
        """Envía una notificación de escritorio al usuario."""
        if shutil.which("notify-send"):
            try:
                subprocess.run(["notify-send", "-a", "App Install", "-i", icon, title, message], timeout=5)
            except Exception:
                pass

    def run_check_and_update(self, initial_delay: int = 180):
        """Ejecuta el ciclo del demonio tras el arranque."""
        print(f"[Daemon] Iniciado. Esperando {initial_delay} segundos tras el arranque...")
        if initial_delay > 0:
            time.sleep(initial_delay)

        # 1. Comprobar si las actualizaciones automáticas están activas
        if not self.is_auto_update_enabled():
            print("[Daemon] Las actualizaciones automáticas están desactivadas por el usuario.")
            return

        # 2. Comprobar conexión a Internet (reintentar durante 60 segundos si está conectando)
        online = False
        for _ in range(6):
            if self.is_online():
                online = True
                break
            time.sleep(10)

        if not online:
            print("[Daemon] Sin conexión a internet. Omitiendo comprobación.")
            return

        # 3. Comprobar idoneidad del procesador
        is_cpu_good, cpu_reason = self.check_cpu_performance()
        print(f"[Daemon] Estado CPU: {cpu_reason}")
        if not is_cpu_good:
            print("[Daemon] Omitiendo actualización automática en segundo plano debido a restricciones de hardware.")
            return

        # 4. Comprobar y aplicar actualizaciones de paquetes del sistema
        print("[Daemon] Comprobando actualizaciones del sistema...")
        updated = False

        if shutil.which("pacman"):
            try:
                # Sincronizar bases de datos en segundo plano
                res = subprocess.run(["pkexec", "pacman", "-Sy"], capture_output=True, timeout=120)
                if res.returncode == 0:
                    # Comprobar si hay paquetes actualizables
                    check = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True, timeout=60)
                    if check.stdout.strip():
                        print(f"[Daemon] Paquetes actualizables encontrados:\n{check.stdout.strip()}")
                        # Ejecutar actualización desatendida
                        upg = subprocess.run(["pkexec", "pacman", "-Su", "--noconfirm"], capture_output=True, timeout=600)
                        if upg.returncode == 0:
                            updated = True
            except Exception as e:
                print(f"[Daemon] Error durante la actualización de pacman: {e}")

        if shutil.which("flatpak"):
            try:
                # Actualizar metadatos y paquetes Flatpak de forma no interactiva
                upg_flat = subprocess.run(["flatpak", "update", "-y", "--noninteractive"], capture_output=True, timeout=180)
                if upg_flat.returncode == 0:
                    out_text = upg_flat.stdout.decode('utf-8', errors='ignore')
                    if "Nothing to do" not in out_text and out_text.strip():
                        updated = True
            except Exception as e:
                print(f"[Daemon] Error actualizando Flatpak: {e}")

        if updated:
            print("[Daemon] Sistema actualizado correctamente.")
            self.send_notification(
                _("Pulsar OS - Actualizaciones"),
                _("El sistema y las aplicaciones se han actualizado automáticamente con éxito.")
            )
        else:
            print("[Daemon] El sistema ya se encuentra al día.")
