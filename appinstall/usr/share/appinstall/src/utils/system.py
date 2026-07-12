import os
import shutil
import subprocess
import webbrowser
from gi.repository import Gtk, Gdk

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
    """Descarga un icono de forma segura y lo guarda en caché local."""
    if not icon_url:
        return ""
    import urllib.parse
    import requests
    
    cache_dir = os.path.expanduser("~/.cache/appinstall/icons")
    os.makedirs(cache_dir, exist_ok=True)
    
    # Nombre seguro para el archivo
    safe_filename = "".join([c if c.isalnum() or c in ".-_" else "_" for c in package_id])
    
    ext = ".png"
    try:
        parsed = urllib.parse.urlparse(icon_url)
        path_ext = os.path.splitext(parsed.path)[1]
        if path_ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico"]:
            ext = path_ext
    except:
        pass
        
    local_path = os.path.join(cache_dir, f"{safe_filename}{ext}")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return local_path
        
    try:
        r = requests.get(icon_url, headers={"User-Agent": "AppInstall/1.0"}, timeout=3)
        if r.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(r.content)
            return local_path
    except Exception as e:
        print(f"Error downloading icon {icon_url}: {e}")
        
    return ""

