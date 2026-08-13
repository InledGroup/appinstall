import os
import subprocess
import shutil
import tempfile
import requests
from typing import List, Dict
from src.domain.ports import PackageManager

class AurAdapter(PackageManager):
    def __init__(self):
        self._meta_cache = {}

    def is_available(self) -> bool:
        """Comprueba si el sistema es Arch Linux y tiene pacman."""
        return shutil.which('pacman') is not None

    def search(self, query: str) -> List[Dict[str, str]]:
        if not self.is_available():
            return []
            
        results = []
        try:
            # Consultar la API RPC v5 de AUR
            url = f"https://aur.archlinux.org/rpc/v5/search/{query}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                packages = data.get("results", [])
                # Ordenar por popularidad descendente y tomar los primeros 15
                packages = sorted(packages, key=lambda x: x.get("Popularity", 0), reverse=True)
                for pkg in packages[:15]:
                    name = pkg.get("Name")
                    desc = pkg.get("Description", "")
                    version = pkg.get("Version", "")
                    votes = pkg.get("NumVotes", 0)
                    
                    # Guardar en caché para detalles rápidos
                    self._meta_cache[name] = {
                        'developer': pkg.get('Maintainer', ''),
                        'verified': False,
                        'version': version,
                        'description': desc
                    }
                    
                    results.append({
                        'name': name,
                        'display_name': name,
                        'desc': desc or f"Versión {version} ({votes} votos)",
                        'source': 'aur',
                        'icon': 'system-software-install-symbolic'
                    })
        except Exception as e:
            print(f"AUR API search error: {e}")
            
        return results

    def list_installed(self) -> List[str]:
        if not self.is_available():
            return []
        try:
            # Obtener paquetes "extranjeros" (instalados desde AUR u otras fuentes externas)
            output = subprocess.check_output(['pacman', '-Qm'], timeout=10, stderr=subprocess.DEVNULL).decode('utf-8')
            return [line.split()[0] for line in output.split('\n') if line.strip()]
        except Exception as e:
            print(f"Error listing installed AUR packages: {e}")
            return []

    def get_pkgbuild(self, package: str) -> str:
        """Obtiene el contenido del PKGBUILD de un paquete del AUR."""
        # 1. Intentar descargar el PKGBUILD directamente desde el git del AUR
        try:
            url = f"https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h={package}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and r.text.strip():
                return r.text
        except Exception as e:
            print(f"AUR PKGBUILD fetch error: {e}")
            
        # 2. Fallback: clonar el repositorio y leer el archivo local
        tmp_dir = tempfile.mkdtemp(prefix=f"appinstall_pkgbuild_")
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', f'https://aur.archlinux.org/{package}.git', tmp_dir],
                check=True, timeout=60, capture_output=True
            )
            pkgbuild_path = os.path.join(tmp_dir, 'PKGBUILD')
            if os.path.exists(pkgbuild_path):
                with open(pkgbuild_path, 'r', encoding='utf-8', errors='replace') as f:
                    return f.read()
        except Exception as e:
            print(f"AUR PKGBUILD clone fallback error: {e}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            
        return ""

    def install(self, package: str) -> List[str]:
        # Instalación nativa desde el AUR sin depender de yay ni paru:
        # 1. Asegura que git y base-devel estén disponibles
        # 2. Clona el repositorio del paquete
        # 3. Compila con makepkg (instala dependencias con pacman)
        # 4. Instala el paquete compilado; si pacman detecta archivos en conflicto
        #    con otro paquete, se reintenta sobrescribiendo SOLO esos archivos
        #    (mismo comportamiento que los ayudantes de AUR).
        temp_dir = f"/tmp/appinstall_aur_{package}"
        script = f"""\
if ! command -v git >/dev/null 2>&1; then ${{APPINSTALL_SUDO:-sudo}} pacman -S --needed --noconfirm git; fi && \\
rm -rf "{temp_dir}" && \\
git clone --depth 1 https://aur.archlinux.org/{package}.git "{temp_dir}" && \\
cd "{temp_dir}" && \\
if ! pacman -Qi base-devel >/dev/null 2>&1; then ${{APPINSTALL_SUDO:-sudo}} pacman -S --needed --noconfirm base-devel; fi && \\
if ! makepkg -s --noconfirm --needed; then
    exit 1
fi
pkgfile="$(ls -1 *.pkg.tar.* 2>/dev/null | head -n1)"
if [ -z "$pkgfile" ]; then
    echo "No se encontró el paquete compilado." >&2
    exit 1
fi
# Ruta absoluta: pkexec (elevación gráfica) no conserva el directorio de trabajo,
# así que una ruta relativa haría que pacman no encuentre el paquete.
pkgfile="$PWD/$pkgfile"
tmpout="$(mktemp)"
trap 'rm -f "$tmpout"; rm -rf "{temp_dir}"' EXIT
${{APPINSTALL_SUDO:-sudo}} pacman -U --noconfirm "$pkgfile" 2>&1 | tee "$tmpout"
rc=${{PIPESTATUS[0]}}
if [ "$rc" -ne 0 ]; then
    # Pacman devuelve las líneas de conflicto como: <paquete>: /ruta <motivo>
    conflicts="$(sed -n 's/^[^:]*: \\(\\/[^ ]*\\) .*/\\1/p' "$tmpout" | sort -u)"
    if [ -n "$conflicts" ]; then
        echo ""
        echo "=== Se detectaron archivos en conflicto con otro paquete; se reintenta sobrescribiéndolos ==="
        extra=""
        for f in $conflicts; do
            extra="$extra --overwrite $f"
        done
        ${{APPINSTALL_SUDO:-sudo}} pacman -U --noconfirm $extra "$pkgfile"
        rc=$?
    fi
fi
exit "$rc"
"""
        return ['sh', '-c', script]

    def install_multiple(self, packages: List[str]) -> List[str]:
        # Sin ayudante de AUR: instalar uno a uno usando el método nativo
        commands = []
        for pkg in packages:
            commands.extend(self.install(pkg))
        return commands

    def install_local(self, file_path: str) -> List[str]:
        return ['pkexec', 'pacman', '-U', '--noconfirm', file_path]

    def uninstall(self, package: str) -> List[str]:
        # Para desinstalar un paquete AUR, usamos el gestor nativo pacman
        return ['pkexec', 'pacman', '-Rns', '--noconfirm', package]

    def get_package_info(self, package_name: str) -> Dict[str, str]:
        info = {
            'name': package_name,
            'version': 'N/A',
            'description': 'Paquete del Arch User Repository (AUR).',
            'size': 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'aur',
            'developer': '',
            'verified': False
        }
        
        cached = self._meta_cache.get(package_name, {})
        if cached:
            info['version'] = cached.get('version', 'N/A')
            info['description'] = cached.get('description', '')
            info['developer'] = cached.get('developer', '')
            info['verified'] = cached.get('verified', False)
        
        try:
            url = f"https://aur.archlinux.org/rpc/v5/info/{package_name}"
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if results:
                    pkg = results[0]
                    info['name'] = pkg.get('Name', package_name)
                    info['version'] = pkg.get('Version', 'N/A')
                    info['description'] = pkg.get('Description', '')
                    info['developer'] = pkg.get('Maintainer', '')
                    info['verified'] = False
                    
                    licenses = pkg.get('License', [])
                    if licenses:
                        info['license'] = ", ".join(licenses)
                        
                    url_upstream = pkg.get('URL', '')
                    if url_upstream:
                        info['website'] = url_upstream
                    
                    # Dependencias desde la API del AUR
                    depends = list(pkg.get('Depends', []) or [])
                    makedepends = list(pkg.get('MakeDepends', []) or [])
                    checkdepends = list(pkg.get('CheckDepends', []) or [])
                    deps = depends + makedepends + checkdepends
                    seen = set()
                    uniq_deps = []
                    for d in deps:
                        if d not in seen:
                            seen.add(d)
                            uniq_deps.append(d)
                    if uniq_deps:
                        info['dependencies'] = uniq_deps
        except Exception as e:
            print(f"Error fetching AUR package info: {e}")
            
        # Cargar el PKGBUILD para mostrarlo antes de instalar
        info['pkgbuild'] = self.get_pkgbuild(package_name)
            
        return info

    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        # AUR local no aplica como archivo directo
        return {
            'name': os.path.basename(file_path),
            'version': 'N/A',
            'description': 'Paquete Arch Linux local.',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB" if os.path.exists(file_path) else 'N/A',
            'icon': 'system-software-install-symbolic',
            'source': 'aur'
        }

    # Métodos de la interfaz PackageManager que no aplican directamente
    def update_cache(self) -> List[str]:
        return ['pkexec', 'pacman', '-Sy']
        
    def clean_cache(self) -> List[str]:
        return []
        
    def autoremove(self) -> List[str]:
        return []
        
    def fix_broken(self) -> List[str]:
        return []
        
    def get_cache_directory(self) -> str:
        return "/var/cache/pacman/pkg"
        
    def install_clamav(self) -> List[str]:
        return []
        
    def upgrade_system(self) -> List[str]:
        return ['pkexec', 'pacman', '-Syu', '--noconfirm']
