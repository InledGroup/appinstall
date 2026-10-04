import os
import shutil
import socket
import subprocess
import webbrowser
import re
from gi.repository import Gtk, Gdk

def get_gnome_shell_version() -> str:
    """Detect the current GNOME Shell major version (e.g., '50', '47')."""
    try:
        out = subprocess.check_output(['gnome-shell', '--version'], timeout=2).decode()
        m = re.search(r'(\d+)(?:\.(\d+))?', out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "50"

def get_gnome_shell_full_version() -> str:
    """Detect full GNOME Shell version (e.g., '50.5')."""
    try:
        out = subprocess.check_output(['gnome-shell', '--version'], timeout=2).decode()
        m = re.search(r'(\d+(?:\.\d+)+)', out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""

def check_gnome_shell_compatibility(shell_versions_or_map, current_version: str = None):
    """
    Check if a GNOME extension supports the user's running GNOME shell version.
    Returns (is_compatible: bool, badge_text: str, tooltip: str)
    """
    if current_version is None:
        current_version = get_gnome_shell_version()

    versions = []
    if isinstance(shell_versions_or_map, dict):
        versions = list(shell_versions_or_map.keys())
    elif isinstance(shell_versions_or_map, (list, set, tuple)):
        versions = [str(v) for v in shell_versions_or_map]

    if not versions:
        return True, f"GNOME {current_version}", f"Compatible con GNOME Shell {current_version}"

    # Direct match or major match
    for v in versions:
        if v == current_version or v.startswith(f"{current_version}."):
            return True, f"GNOME {current_version}", f"Certificada para GNOME Shell {current_version}"

    def parse_ver(v_str):
        try:
            return tuple(int(p) for p in re.findall(r'\d+', str(v_str)))
        except Exception:
            return (0,)

    sorted_v = sorted(versions, key=parse_ver)
    max_v = sorted_v[-1] if sorted_v else "N/A"
    return False, f"Hasta GNOME {max_v}", f"Soporta hasta GNOME {max_v} (tu versión es {current_version})"

def has_internet(timeout=3.0):
    """Comprueba rápidamente si hay conexión a internet."""
    try:
        with socket.create_connection(("flathub.org", 443), timeout=timeout):
            return True
    except Exception:
        return False

def get_brew_path():
    """Busca la ruta de Homebrew de forma más robusta."""
    common_paths = [
        '/home/linuxbrew/.linuxbrew/bin/brew',
        '/usr/local/bin/brew',
        '/opt/homebrew/bin/brew'
    ]
    for path in common_paths:
        if os.path.exists(path):
            return path
    return shutil.which('brew')

BREW_PATH = get_brew_path()
HAS_BREW = BREW_PATH is not None

def safe_open_url(url):
    """Opens a URL safely with better error handling."""
    try:
        if os.name == 'posix':
            subprocess.Popen(['xdg-open', url])
        else:
            webbrowser.open(url)
        return True
    except Exception as e:
        print(f"Error opening URL: {str(e)}")
        return False

def get_safe_window_size(default_width, default_height, scale_factor=0.8):
    """Obtiene un tamaño de ventana seguro que no exceda los límites de la pantalla."""
    try:
        display = Gdk.Display.get_default()
        if display:
            monitor = display.get_monitors().get_item(0)
            if monitor:
                geometry = monitor.get_geometry()
                max_width = int(geometry.width * scale_factor)
                max_height = int(geometry.height * scale_factor)
                
                min_width = min(400, geometry.width - 100)
                min_height = min(300, geometry.height - 100)
                
                width = max(min_width, min(default_width, max_width))
                height = max(min_height, min(default_height, max_height))
                
                return width, height
    except Exception as e:
        print(f"Error obteniendo tamaño de pantalla: {e}")
    
    return default_width, default_height

def get_cached_icon(icon_url: str, package_id: str) -> str:
    """Descarga un icono de forma segura (PNG, SVG, GIF, JPG, ICO, WebP) y lo guarda en caché local."""
    if not icon_url:
        return ""
    import urllib.parse
    import requests
    
    cache_dir = os.path.expanduser("~/.cache/appinstall/icons")
    os.makedirs(cache_dir, exist_ok=True)
    
    safe_filename = "".join([c if c.isalnum() or c in ".-_" else "_" for c in package_id])
    
    # Check if already cached with any supported extension
    for candidate_ext in [".png", ".svg", ".gif", ".jpg", ".jpeg", ".webp", ".ico"]:
        candidate = os.path.join(cache_dir, f"{safe_filename}{candidate_ext}")
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            return candidate
        
    try:
        r = requests.get(icon_url, headers={"User-Agent": "AppInstall/1.0"}, timeout=6)
        if r.status_code == 200 and r.content:
            ct = r.headers.get("Content-Type", "").lower()
            ext = ".png"
            if "svg" in ct or b"<svg" in r.content[:200].lower():
                ext = ".svg"
            elif "gif" in ct or r.content.startswith(b"GIF"):
                ext = ".gif"
            elif "webp" in ct or (r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"):
                ext = ".webp"
            elif "jpeg" in ct or "jpg" in ct or r.content.startswith(b"\xff\xd8\xff"):
                ext = ".jpg"
            elif "ico" in ct or r.content.startswith(b"\x00\x00\x01\x00"):
                ext = ".ico"

            local_path = os.path.join(cache_dir, f"{safe_filename}{ext}")
            with open(local_path, "wb") as f:
                f.write(r.content)
            return local_path
    except Exception as e:
        print(f"Error downloading icon {icon_url}: {e}")
        
    return ""

def create_app_icon_widget(icon_path_or_url_or_name: str, size: int = 44, fallback: str = "system-software-install-symbolic", package_id: str = "app") -> Gtk.Widget:
    """Creates a GTK4 widget properly rendering SVG, GIF, PNG, JPG, WebP, ICO, or symbolic icon strictly constrained to size x size."""
    import gi
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import GdkPixbuf, Gdk

    path = icon_path_or_url_or_name
    if path and (path.startswith("http://") or path.startswith("https://")):
        cached = get_cached_icon(path, package_id)
        if cached and os.path.exists(cached):
            path = cached

    widget = None
    if path and os.path.isfile(path):
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
            tex = Gdk.Texture.new_for_pixbuf(pix)
            img = Gtk.Image.new_from_paintable(tex)
            img.set_pixel_size(size)
            widget = img
        except Exception:
            try:
                img = Gtk.Image.new_from_file(path)
                img.set_pixel_size(size)
                widget = img
            except Exception:
                pass

    if widget is None:
        icon_name = path if (path and not os.path.isabs(path) and not path.startswith("http")) else fallback
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(size)
        widget = img

    box = Gtk.Box()
    box.set_size_request(size, size)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)
    box.set_hexpand(False)
    box.set_vexpand(False)
    box.add_css_class("app-card-icon")
    box.append(widget)
    return box

def get_cached_screenshot(screenshot_url: str, prefix: str) -> str:
    """Descarga una imagen de demo/screenshot (PNG, JPG, WebP, SVG, GIF) y la almacena en caché."""
    if not screenshot_url:
        return ""
    import urllib.parse
    import hashlib
    import requests

    cache_dir = os.path.expanduser("~/.cache/appinstall/screenshots")
    os.makedirs(cache_dir, exist_ok=True)

    url_hash = hashlib.md5(screenshot_url.encode("utf-8")).hexdigest()[:10]
    safe_prefix = "".join([c if c.isalnum() or c in ".-_" else "_" for c in prefix])
    
    # Check if already cached with any supported extension
    for candidate_ext in [".gif", ".png", ".jpg", ".jpeg", ".svg", ".webp"]:
        candidate = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}{candidate_ext}")
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            return candidate

    try:
        r = requests.get(screenshot_url, headers={"User-Agent": "AppInstall/1.0"}, timeout=10)
        if r.status_code == 200 and r.content:
            ct = r.headers.get("Content-Type", "").lower()
            ext = ".jpg"
            if "svg" in ct or b"<svg" in r.content[:200].lower():
                ext = ".svg"
            elif "gif" in ct or r.content.startswith(b"GIF"):
                ext = ".gif"
            elif "png" in ct or r.content.startswith(b"\x89PNG\r\n\x1a\n"):
                ext = ".png"
            elif "webp" in ct or (r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"):
                ext = ".webp"

            local_path = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}{ext}")
            with open(local_path, "wb") as f:
                f.write(r.content)
            return local_path
    except Exception as e:
        print(f"Error downloading screenshot {screenshot_url}: {e}")

    return ""

def is_gnome_desktop() -> bool:
    """Check if currently running within a GNOME desktop environment."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    session = os.environ.get("DESKTOP_SESSION", "").upper()
    if any(k in desktop for k in ["GNOME", "PULSAR", "UBUNTU", "PANTHEON"]) or any(k in session for k in ["GNOME", "PULSAR", "UBUNTU", "PANTHEON"]):
        return True
    try:
        res = subprocess.run(["pgrep", "-x", "gnome-shell"], capture_output=True)
        if res.returncode == 0:
            return True
    except Exception:
        pass
    return False

