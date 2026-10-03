import os
import shutil
import socket
import subprocess
import webbrowser
from gi.repository import Gtk, Gdk

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
    
    ext = ".png"
    try:
        parsed = urllib.parse.urlparse(icon_url)
        path_ext = os.path.splitext(parsed.path)[1].lower()
        if path_ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".webp"]:
            ext = path_ext
    except Exception:
        pass
        
    local_path = os.path.join(cache_dir, f"{safe_filename}{ext}")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path
        
    try:
        r = requests.get(icon_url, headers={"User-Agent": "AppInstall/1.0"}, timeout=5)
        if r.status_code == 200 and r.content:
            ct = r.headers.get("Content-Type", "").lower()
            if ("svg" in ct or b"<svg" in r.content[:100].lower()) and not local_path.endswith(".svg"):
                local_path = os.path.join(cache_dir, f"{safe_filename}.svg")
            elif ("gif" in ct or r.content.startswith(b"GIF")) and not local_path.endswith(".gif"):
                local_path = os.path.join(cache_dir, f"{safe_filename}.gif")
            elif ("webp" in ct or b"WEBP" in r.content[:20]) and not local_path.endswith(".webp"):
                local_path = os.path.join(cache_dir, f"{safe_filename}.webp")

            with open(local_path, "wb") as f:
                f.write(r.content)
            return local_path
    except Exception as e:
        print(f"Error downloading icon {icon_url}: {e}")
        
    return ""

def create_app_icon_widget(icon_path_or_url_or_name: str, size: int = 44, fallback: str = "system-software-install-symbolic", package_id: str = "app") -> Gtk.Widget:
    """Creates a GTK4 widget (Gtk.Image or Gtk.Picture) properly rendering SVG, GIF, PNG, JPG, WebP, ICO, or symbolic icon."""
    if not icon_path_or_url_or_name:
        img = Gtk.Image.new_from_icon_name(fallback)
        img.set_pixel_size(size)
        return img

    path = icon_path_or_url_or_name
    if path.startswith("http://") or path.startswith("https://"):
        cached = get_cached_icon(path, package_id)
        if cached and os.path.exists(cached):
            path = cached

    if os.path.isfile(path):
        lower = path.lower()
        if lower.endswith((".svg", ".gif", ".webp", ".png", ".jpg", ".jpeg", ".ico")):
            try:
                pic = Gtk.Picture.new_for_filename(path)
                pic.set_size_request(size, size)
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_can_shrink(True)
                return pic
            except Exception:
                pass
        try:
            img = Gtk.Image.new_from_file(path)
            img.set_pixel_size(size)
            return img
        except Exception:
            pass

    # Symbolic or named theme icon
    img = Gtk.Image.new_from_icon_name(path if path else fallback)
    img.set_pixel_size(size)
    return img

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
    
    ext = ".jpg"
    try:
        parsed = urllib.parse.urlparse(screenshot_url)
        path_ext = os.path.splitext(parsed.path)[1].lower()
        if path_ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"]:
            ext = path_ext
    except Exception:
        pass

    local_path = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}{ext}")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path

    try:
        r = requests.get(screenshot_url, headers={"User-Agent": "AppInstall/1.0"}, timeout=8)
        if r.status_code == 200 and r.content:
            ct = r.headers.get("Content-Type", "").lower()
            if "svg" in ct and not local_path.endswith(".svg"):
                local_path = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}.svg")
            elif "gif" in ct and not local_path.endswith(".gif"):
                local_path = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}.gif")
            elif "png" in ct and not local_path.endswith(".png"):
                local_path = os.path.join(cache_dir, f"{safe_prefix}_{url_hash}.png")

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

