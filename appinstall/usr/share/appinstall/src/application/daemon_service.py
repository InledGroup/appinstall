import os
import sys
import time
import json
import subprocess
import socket
import shutil

from src.infrastructure.services.localization import _

try:
    import fcntl
except ImportError:  # pragma: no cover - solo Linux
    fcntl = None


class DaemonService:
    """Demonio de segundo plano para comprobación y aplicación automática de actualizaciones en Pulsar OS."""

    CONFIG_PATHS = [
        os.path.expanduser("~/.config/appinstall/config.json"),
        "/etc/appinstall/config.json"
    ]

    # Fichero de bloqueo: evita que corran varios ciclos simultáneamente
    # (el demonio de sesión y la aplicación abierta a la vez, por ejemplo).
    LOCK_PATH = os.path.expanduser("~/.cache/appinstall/autoupdate.lock")

    # Horas entre comprobaciones automáticas
    INTERVAL_HOURS = 6

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

    def _acquire_lock(self):
        """Bloquea la instancia única del ciclo. Devuelve el descriptor o None."""
        if fcntl is None:
            return None
        try:
            os.makedirs(os.path.dirname(self.LOCK_PATH), exist_ok=True)
            fd = os.open(self.LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return None
            os.truncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except OSError:
            return None

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
                return False, f"Carga del sistema demasiada alta ({load1:.2f} para {cores} núcleos)"
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

    # ── Instalación de actualizaciones del sistema ──────────────────────────

    def _sudo_prefix(self):
        """Comando para obtener privilegios (pkexec en escritorios con polkit)."""
        if os.geteuid() == 0:
            return []
        if shutil.which("pkexec"):
            return ["pkexec"]
        return None

    def install_system_updates(self) -> int:
        """English: Actually install the pending system updates, asking polkit
        for the required privileges. Returns the number of packages updated.
        Español: Instala realmente las actualizaciones pendientes del sistema,
        pidiendo los privilegios necesarios a polkit."""
        prefix = self._sudo_prefix()
        if prefix is None:
            print("[Daemon] Sin pkexec ni privilegios: solo se notificarán las actualizaciones.")
            return 0

        updated = 0

        # Debian / Ubuntu / Pulsar OS
        if shutil.which("apt-get"):
            try:
                subprocess.run(prefix + ["apt-get", "update", "-qq"],
                               capture_output=True, timeout=300)
                res = subprocess.run(
                    prefix + ["apt-get", "upgrade", "-y", "-o", "Dpkg::Options::=--force-confold"],
                    capture_output=True, timeout=1800)
                if res.returncode == 0:
                    updated += 1
                    print("[Daemon] APT actualizado correctamente.")
                else:
                    print(f"[Daemon] APT devolvió {res.returncode}.")
            except Exception as e:
                print(f"[Daemon] Error actualizando con APT: {e}")

        # Arch Linux / Pacman
        if shutil.which("pacman"):
            try:
                res = subprocess.run(prefix + ["pacman", "-Syu", "--noconfirm"],
                                     capture_output=True, timeout=1800)
                if res.returncode == 0:
                    updated += 1
                    print("[Daemon] Pacman actualizado correctamente.")
                else:
                    print(f"[Daemon] Pacman devolvió {res.returncode}.")
            except Exception as e:
                print(f"[Daemon] Error actualizando con Pacman: {e}")

        # Fedora / DNF
        if shutil.which("dnf"):
            try:
                res = subprocess.run(prefix + ["dnf", "upgrade", "-y"],
                                     capture_output=True, timeout=1800)
                if res.returncode == 0:
                    updated += 1
                    print("[Daemon] DNF actualizado correctamente.")
            except Exception as e:
                print(f"[Daemon] Error actualizando con DNF: {e}")

        return updated

    # ── Ciclo del demonio ───────────────────────────────────────────────────

    def run_loop(self, first_delay_seconds: int = 180, interval_hours: float = None):
        """English: Keep running update cycles in the background. The config is
        re-read on every cycle, so toggling automatic updates in the app takes
        effect without restarting anything. Only one instance runs at a time.
        Español: Mantiene en segundo plano un ciclo de actualizaciones
        periódico. La configuración se relée en cada ciclo, así que activar o
        desactivar las actualizaciones automáticas en la aplicación surte
        efecto sin reiniciar nada. Solo corre una instancia a la vez."""
        interval = interval_hours or self.INTERVAL_HOURS
        lock = self._acquire_lock()
        if lock is None:
            print("[Daemon] Ya hay otro ciclo de actualizaciones automáticas en marcha.")
            return

        print(f"[Daemon] Bucle iniciado. Primera comprobación en {first_delay_seconds}s, "
              f"después cada {interval}h.")
        if first_delay_seconds > 0:
            time.sleep(first_delay_seconds)

        try:
            while True:
                if self.is_auto_update_enabled():
                    try:
                        self.run_check_and_update(initial_delay=0)
                    except Exception as e:
                        print(f"[Daemon] Error en el ciclo de actualizaciones: {e}")
                else:
                    print("[Daemon] Actualizaciones automáticas desactivadas. Esperando...")
                time.sleep(interval * 3600)
        finally:
            try:
                os.close(lock)
            except OSError:
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
        updates_available_count = 0

        # Debian / Ubuntu / Pulsar OS APT
        if shutil.which("apt-get"):
            try:
                check = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=60)
                lines = [l for l in check.stdout.strip().splitlines() if "/" in l and "Listing..." not in l]
                if lines:
                    updates_available_count += len(lines)
                    print(f"[Daemon] {len(lines)} paquetes actualizables encontrados en APT.")
            except Exception as e:
                print(f"[Daemon] Error comprobando APT: {e}")

        # Arch Linux / Pacman
        if shutil.which("pacman"):
            try:
                check = subprocess.run(["pacman", "-Qu"], capture_output=True, text=True, timeout=60)
                lines = [l for l in check.stdout.strip().splitlines() if l.strip()]
                if lines:
                    updates_available_count += len(lines)
                    print(f"[Daemon] {len(lines)} paquetes actualizables encontrados en Pacman.")
            except Exception as e:
                print(f"[Daemon] Error comprobando Pacman: {e}")

        # Fedora / DNF
        if shutil.which("dnf"):
            try:
                check = subprocess.run(["dnf", "check-update", "-q"], capture_output=True, text=True, timeout=60)
                lines = [l for l in check.stdout.strip().splitlines() if l.strip()]
                if lines:
                    updates_available_count += len(lines)
            except Exception as e:
                print(f"[Daemon] Error comprobando DNF: {e}")

        # Flatpak (no necesita privilegios)
        if shutil.which("flatpak"):
            try:
                upg_flat = subprocess.run(["flatpak", "update", "-y", "--noninteractive"], capture_output=True, timeout=600)
                if upg_flat.returncode == 0:
                    out_text = upg_flat.stdout.decode('utf-8', errors='ignore')
                    if "Nothing to do" not in out_text and out_text.strip():
                        updated = True
            except Exception as e:
                print(f"[Daemon] Error actualizando Flatpak: {e}")

        # Actualizaciones del sistema (ahora sí se instalan, no solo se notifican)
        if updates_available_count > 0 and self.install_system_updates() > 0:
            updated = True

        if updated:
            print("[Daemon] Sistema actualizado correctamente.")
            self.send_notification(
                _("Pulsar OS - Actualizaciones"),
                _("Las aplicaciones se han actualizado automáticamente con éxito.")
            )
        elif updates_available_count > 0:
            self.send_notification(
                _("Pulsar OS - Actualizaciones"),
                _("Hay {} actualizaciones del sistema disponibles para instalar.").format(updates_available_count)
            )
        else:
            print("[Daemon] El sistema ya se encuentra al día.")
