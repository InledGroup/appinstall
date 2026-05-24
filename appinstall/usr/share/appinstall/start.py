import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, GLib, Gio, Gdk, Adw
import subprocess
import os
import threading
import webbrowser
import requests
import time
import sys
import shutil
from packaging import version

# Versión actual de la aplicación
CURRENT_VERSION = "11.0"  # Esto se cambia según haya una nueva release
GITHUB_REPO = "InledGroup/appinstall"

import locale
import gettext

# Configurar localización
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locale')
if not os.path.exists(LOCALE_DIR):
    LOCALE_DIR = '/app/share/locale'  # Fallback for Flatpak
if not os.path.exists(LOCALE_DIR):
    LOCALE_DIR = '/usr/share/locale'  # Fallback for system install

try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass

gettext.bindtextdomain('appinstall', LOCALE_DIR)
gettext.textdomain('appinstall')
_ = gettext.gettext

# Configurar el tema de iconos para incluir directorios locales (útil para ejecución sin instalar)
def setup_icon_theme():
    try:
        display = Gdk.Display.get_default()
        if not display:
            # Si no hay display aún, probamos a obtener el tema por defecto
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        else:
            theme = Gtk.IconTheme.get_for_display(display)
            
        local_dir = os.path.dirname(os.path.abspath(__file__))
        theme.add_search_path(local_dir)
        theme.add_search_path(os.path.join(local_dir, "appinstall/usr/share/pixmaps"))
        # Añadir también el directorio actual por si acaso
        theme.add_search_path(os.getcwd())
    except Exception as e:
        print(f"Advertencia al configurar tema de iconos: {e}")

class PackageManager:
    def search(self, query):
        raise NotImplementedError()
    def list_installed(self):
        raise NotImplementedError()
    def install(self, package):
        raise NotImplementedError()
    def install_multiple(self, packages):
        raise NotImplementedError()
    def install_local(self, file_path):
        raise NotImplementedError()
    def uninstall(self, package):
        raise NotImplementedError()
    def update_cache(self):
        raise NotImplementedError()
    def clean_cache(self):
        raise NotImplementedError()
    def autoremove(self):
        raise NotImplementedError()
    def fix_broken(self):
        raise NotImplementedError()
    def get_cache_directory(self):
        raise NotImplementedError()
    def install_clamav(self):
        raise NotImplementedError()

class AptManager(PackageManager):
    def search(self, query):
        results = []
        try:
            output = subprocess.check_output(['apt-cache', 'search', query], timeout=10).decode('utf-8')
            for line in output.split('\n'):
                if line.strip():
                    parts = line.split(' - ', 1)
                    name = parts[0].strip()
                    desc = parts[1].strip() if len(parts) > 1 else ""
                    results.append({'name': name, 'desc': desc, 'source': 'apt'})
        except:
            pass
        return results

    def list_installed(self):
        try:
            output = subprocess.check_output(['dpkg', '--get-selections'], timeout=15).decode('utf-8')
            return [line.split()[0] for line in output.split('\n') 
                    if line.strip() and len(line.split()) > 1 and line.split()[1] == 'install']
        except:
            return []

    def install(self, package):
        return ['pkexec', 'apt-get', 'install', '-y', package]

    def install_multiple(self, packages):
        return ['pkexec', 'apt-get', 'install', '-y'] + packages

    def install_local(self, file_path):
        return ['pkexec', 'dpkg', '-i', file_path]

    def uninstall(self, package):
        return ['pkexec', 'apt-get', 'remove', '-y', package]

    def update_cache(self):
        return ['pkexec', 'apt-get', 'update']

    def clean_cache(self):
        return ['pkexec', 'apt-get', 'clean']

    def autoremove(self):
        return ['pkexec', 'apt-get', 'autoremove', '-y']

    def fix_broken(self):
        return ['pkexec', 'apt-get', 'install', '-f', '-y']

    def get_cache_directory(self):
        return "/var/cache/apt/archives"

    def install_clamav(self):
        return ['pkexec', 'apt-get', 'install', '-y', 'clamav', 'clamav-daemon', 'clamav-freshclam']

class DnfManager(PackageManager):
    def search(self, query):
        results = []
        try:
            # Aumentamos el timeout a 30s ya que dnf puede ser muy lento refrescando caché
            # Usamos --quiet para evitar ruidos de metadatos en la salida
            output = subprocess.check_output(['dnf', 'search', '--quiet', query], timeout=30).decode('utf-8', errors='ignore')
            
            # dnf search puede tener formatos distintos según versión (DNF 4 vs DNF 5)
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Formato clásico DNF 4: "Name : Summary"
                if ' : ' in line:
                    parts = line.split(' : ', 1)
                    name = parts[0].strip()
                    
                    # Limpiar arquitectura si está presente (e.g. name.x86_64)
                    archs = ('.x86_64', '.i686', '.noarch', '.armv7hl', '.aarch64', '.ppc64le', '.s390x')
                    for arch in archs:
                        if name.endswith(arch):
                            name = name[:-len(arch)]
                            break
                            
                    desc = parts[1].strip()
                    results.append({'name': name, 'desc': desc, 'source': 'dnf'})
                
                # Formato tabular DNF 5: "ID | Summary"
                elif '|' in line and not line.startswith('---'):
                    parts = line.split('|', 1)
                    name = parts[0].strip()
                    desc = parts[1].strip()
                    # Ignorar cabeceras
                    if name.lower() not in ('id', 'nombre', 'name'):
                        results.append({'name': name, 'desc': desc, 'source': 'dnf'})
        except Exception as e:
            print(f"Error en dnf search: {e}")
            pass
        return results

    def list_installed(self):
        try:
            output = subprocess.check_output(['rpm', '-qa', '--qf', '%{NAME}\\n'], timeout=15).decode('utf-8')
            return [line.strip() for line in output.split('\n') if line.strip()]
        except:
            return []

    def install(self, package):
        return ['pkexec', 'dnf', 'install', '-y', package]

    def install_multiple(self, packages):
        return ['pkexec', 'dnf', 'install', '-y'] + packages

    def install_local(self, file_path):
        return ['pkexec', 'dnf', 'install', '-y', file_path]

    def uninstall(self, package):
        return ['pkexec', 'dnf', 'remove', '-y', package]

    def update_cache(self):
        return ['pkexec', 'dnf', 'makecache']

    def clean_cache(self):
        return ['pkexec', 'dnf', 'clean', 'all']

    def autoremove(self):
        return ['pkexec', 'dnf', 'autoremove', '-y']

    def fix_broken(self):
        # dnf doesn't have a direct equivalent to apt install -f, but it handles deps better
        return ['pkexec', 'dnf', 'check']

    def get_cache_directory(self):
        return "/var/cache/dnf"

    def install_clamav(self):
        return ['pkexec', 'dnf', 'install', '-y', 'clamav', 'clamav-update', 'clamd']

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

def get_package_manager():
    if shutil.which('dnf'):
        return DnfManager()
    elif shutil.which('yum'):
        # Could create a YumManager but DnfManager is usually compatible enough
        return DnfManager()
    else:
        return AptManager()

pkg_manager = get_package_manager()

# Aplicar CSS para un estilo GNOME moderno
def load_css():
    css_provider = Gtk.CssProvider()
    
    # CSS moderno integrado para GNOME
    css_data = """
    .main-window {
        background: @window_bg_color;
    }
    
    .header-bar {
        background: @headerbar_bg_color;
        color: @headerbar_fg_color;
    }
    
    .card {
        background: @card_bg_color;
        border-radius: 12px;
        padding: 24px;
        margin: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .title-label {
        font-size: 1.2em;
        font-weight: bold;
        color: @window_fg_color;
    }
    
    .subtitle-label {
        font-size: 0.9em;
        color: @insensitive_fg_color;
    }
    
    .action-button {
        background: @accent_bg_color;
        color: @accent_fg_color;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: bold;
    }
    
    .secondary-button {
        border-radius: 8px;
        padding: 12px 24px;
    }
    
    .destructive-button {
        background: @error_bg_color;
        color: @error_fg_color;
        border-radius: 8px;
    }
    
    .search-entry {
        border-radius: 8px;
        padding: 8px 12px;
    }
    
    .progress-bar {
        border-radius: 4px;
    }
    
    .status-label {
        color: @insensitive_fg_color;
    }
    
    .list-row {
        border-radius: 8px;
        margin: 2px;
    }
    
    .file-chooser-button {
        border: 2px dashed @borders;
        border-radius: 12px;
        padding: 32px;
        background: @view_bg_color;
    }
    
    .file-chooser-button:hover {
        background: @view_hover_bg_color;
        border-color: @accent_bg_color;
    }
    """
    
    try:
        css_provider.load_from_string(css_data)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    except Exception as e:
        print(f"Error al cargar el CSS: {e}")

def safe_open_url(url):
    """Opens a URL safely with better error handling."""
    try:
        # Use subprocess instead of webbrowser for better control
        if os.name == 'posix':  # Linux/Unix
            subprocess.Popen(['xdg-open', url])
        else:  # Fallback to webbrowser
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
                # Usar el factor de escala del ancho y altura de la pantalla
                max_width = int(geometry.width * scale_factor)
                max_height = int(geometry.height * scale_factor)
                
                # Asegurar un tamaño mínimo
                min_width = min(400, geometry.width - 100)
                min_height = min(300, geometry.height - 100)
                
                width = max(min_width, min(default_width, max_width))
                height = max(min_height, min(default_height, max_height))
                
                return width, height
    except Exception as e:
        print(f"Error obteniendo tamaño de pantalla: {e}")
    
    # Fallback a tamaño por defecto
    return default_width, default_height

def check_for_updates():
    """Comprueba las actualizaciones conectando con la API de GitHub con mejor manejo de errores."""
    try:
        # Add a user agent to avoid GitHub API rate limiting
        headers = {'User-Agent': f'AppInstall/{CURRENT_VERSION}'}
        
        # Add timeout and better error handling
        response = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", 
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            release_data = response.json()
            latest_version = release_data['tag_name'].lstrip('v')
            release_url = release_data['html_url']
            
            # Comparar versiones
            if version.parse(latest_version) > version.parse(CURRENT_VERSION):
                return (True, latest_version, release_url)
            return (False, latest_version, release_url)
        elif response.status_code == 403:
            print("Rate limit exceeded or access forbidden. Check GitHub API usage.")
            return None
        else:
            print(f"Error checking for updates: HTTP {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print("Timeout while checking for updates")
        return None
    except requests.exceptions.ConnectionError:
        print("Connection error while checking for updates")
        return None
    except Exception as e:
        print(f"Unexpected error checking for updates: {str(e)}")
        return None

class UpdateDialog(Adw.AlertDialog):
    def __init__(self, parent, latest_version, release_url):
        super().__init__()
        self.set_heading(_("Actualización disponible"))
        self.set_body(_("Versión actual: {}\nNueva versión: {}").format(CURRENT_VERSION, latest_version))
        self.add_response("cancel", _("Recordar más tarde"))
        self.add_response("update", _("Actualizar ahora"))
        self.set_response_appearance("update", Adw.ResponseAppearance.SUGGESTED)
        self.set_default_response("update")
        self.set_close_response("cancel")
        
        self.release_url = release_url

class SystemCleanupWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__()
        self.set_title(_("Limpiar sistema"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(600, 500, 0.8)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Limpiar sistema")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Contenido desplazable para que no se salga de la pantalla
        if height > 450:
            scrolled_main = Gtk.ScrolledWindow()
            scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled_main.set_propagate_natural_height(True)
            toolbar_view.set_content(scrolled_main)

            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            scrolled_main.set_child(main_box)
        else:
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            toolbar_view.set_content(main_box)

        # Título y descripción
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic")
        title_box.prepend(icon)
        
        title_label = Gtk.Label(label=_("Limpieza del sistema"))
        title_label.add_css_class("title-label")
        title_box.append(title_label)
        main_box.append(title_box)
        
        desc_label = Gtk.Label(label=_("Dime qué quieres que limpie y te dejo el sistema reluciente"))
        desc_label.add_css_class("subtitle-label")
        main_box.append(desc_label)

        # Sección de directorios a limpiar
        directories_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        directories_section.add_css_class("card")
        
        dir_title = Gtk.Label(label=_("Directorios a limpiar"))
        dir_title.add_css_class("title-label")
        directories_section.append(dir_title)

        # Lista de checkboxes para directorios
        self.directory_checks = {}
        
        # Definir directorios comunes para limpiar
        self.cleanup_directories = {
            "~/.cache": _("Caché de aplicaciones del usuario"),
            "~/.local/share/Trash": _("Papelera del usuario"),
            "/tmp": _("Archivos temporales del sistema"),
            "~/.thumbnails": _("Miniaturas de imágenes"),
            "/var/tmp": _("Archivos temporales variables"), 
            "~/.config/*/logs": _("Logs de aplicaciones"),
            "/var/log": _("Logs del sistema (requiere privilegios)"),
            "~/.local/share/recently-used.xbel": _("Lista de archivos recientes")
        }
        
        for directory, description in self.cleanup_directories.items():
            check_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            
            check = Gtk.CheckButton()
            check.set_active(True)  # Por defecto activado
            self.directory_checks[directory] = check
            check_box.prepend(check)
            
            # Información del directorio
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            
            dir_label = Gtk.Label(label=directory, xalign=0)
            dir_label.add_css_class("title-label")
            info_box.append(dir_label)
            
            desc_label = Gtk.Label(label=description, xalign=0)
            desc_label.add_css_class("subtitle-label")
            info_box.append(desc_label)
            
            check_box.append(info_box)
            directories_section.append(check_box)

        main_box.append(directories_section)

        # Sección de opciones avanzadas
        advanced_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        advanced_section.add_css_class("card")
        
        adv_title = Gtk.Label(label=_("Opciones avanzadas"))
        adv_title.add_css_class("title-label")
        advanced_section.append(adv_title)

        # Checkbox para limpiar paquetes huérfanos
        orphan_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.orphan_check = Gtk.CheckButton()
        self.orphan_check.set_active(True)
        orphan_box.prepend(self.orphan_check)
        
        orphan_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        orphan_label = Gtk.Label(label=_("Eliminar paquetes huérfanos"), xalign=0)
        orphan_label.add_css_class("title-label")
        orphan_info.append(orphan_label)
        
        orphan_desc = Gtk.Label(label=_("Paquetes que ya no son necesarios"), xalign=0)
        orphan_desc.add_css_class("subtitle-label")
        orphan_info.append(orphan_desc)
        
        orphan_box.append(orphan_info)
        advanced_section.append(orphan_box)

        # Checkbox para limpiar caché de paquetes
        pkg_cache_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.apt_check = Gtk.CheckButton()
        self.apt_check.set_active(True)
        pkg_cache_box.prepend(self.apt_check)
        
        pkg_cache_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pkg_cache_label = Gtk.Label(label=_("Limpiar caché de paquetes"), xalign=0)
        pkg_cache_label.add_css_class("title-label")
        pkg_cache_info.append(pkg_cache_label)
        
        pkg_cache_desc = Gtk.Label(label=_("Archivos de instalación descargados"), xalign=0)
        pkg_cache_desc.add_css_class("subtitle-label")
        pkg_cache_info.append(pkg_cache_desc)
        
        pkg_cache_box.append(pkg_cache_info)
        advanced_section.append(pkg_cache_box)

        main_box.append(advanced_section)

        # Botones de acción
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_margin_top(16)
        
        # Botón analizar
        self.analyze_button = Gtk.Button()
        analyze_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        analyze_icon = Gtk.Image.new_from_icon_name("document-properties-symbolic")
        analyze_box.prepend(analyze_icon)
        analyze_label = Gtk.Label(label=_("Analizar"))
        analyze_box.append(analyze_label)
        self.analyze_button.set_child(analyze_box)
        self.analyze_button.add_css_class("secondary-button")
        self.analyze_button.connect("clicked", self.on_analyze_clicked)
        button_box.append(self.analyze_button)
        
        # Botón limpiar
        self.clean_button = Gtk.Button()
        clean_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        clean_icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic")
        clean_box.prepend(clean_icon)
        clean_label = Gtk.Label(label=_("Limpiar ahora"))
        clean_box.append(clean_label)
        self.clean_button.set_child(clean_box)
        self.clean_button.add_css_class("action-button")
        self.clean_button.connect("clicked", self.on_clean_clicked)
        self.clean_button.set_sensitive(False)
        button_box.append(self.clean_button)

        main_box.append(button_box)

        # Barra de progreso
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_bar.set_visible(False)
        main_box.append(self.progress_bar)

        # Etiqueta de estado
        self.status_label = Gtk.Label(label=_("Selecciona las opciones y presiona 'Analizar'"))
        self.status_label.add_css_class("status-label")
        main_box.append(self.status_label)

        # Variables para almacenar resultados del análisis
        self.analysis_results = {}
        self.total_size = 0

    def on_analyze_clicked(self, button):
        """Analiza el espacio que se puede liberar."""
        self.analyze_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Analizando archivos..."))
        
        thread = threading.Thread(target=self.analyze_cleanup)
        thread.daemon = True
        thread.start()

    def analyze_cleanup(self):
        """Realiza el análisis en un hilo separado."""
        try:
            self.analysis_results = {}
            self.total_size = 0
            
            # Analizar cada directorio seleccionado
            selected_dirs = [d for d, check in self.directory_checks.items() if check.get_active()]
            total_dirs = len(selected_dirs)
            
            for i, directory in enumerate(selected_dirs):
                GLib.idle_add(self.update_progress, i / total_dirs)
                size = self.get_directory_size(directory)
                self.analysis_results[directory] = size
                self.total_size += size
            
            # Analizar paquetes huérfanos si está seleccionado
            if self.orphan_check.get_active():
                GLib.idle_add(self.update_progress, 0.8)
                orphan_size = self.get_orphan_packages_size()
                self.analysis_results["paquetes_huerfanos"] = orphan_size
                self.total_size += orphan_size
            
            # Analizar caché de paquetes si está seleccionado
            if self.apt_check.get_active():
                GLib.idle_add(self.update_progress, 0.9)
                pkg_cache_size = self.get_package_cache_size()
                self.analysis_results["package_cache"] = pkg_cache_size
                self.total_size += pkg_cache_size
            
            GLib.idle_add(self.analysis_complete)
            
        except Exception as e:
            print(f"Error en análisis: {e}")
            GLib.idle_add(self.analysis_error, str(e))

    def get_directory_size(self, directory):
        """Calcula el tamaño de un directorio."""
        import os
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
            # Usar pkg_manager para obtener la lista de paquetes
            packages = pkg_manager.list_installed()
            return len(packages) * 1024 * 1024  # 1MB promedio estimado
        except:
            return 0

    def get_package_cache_size(self):
        """Calcula el tamaño del caché de paquetes."""
        return self._calculate_dir_size(pkg_manager.get_cache_directory())

    def update_progress(self, fraction):
        """Actualiza la barra de progreso."""
        self.progress_bar.set_fraction(fraction)
        return False

    def analysis_complete(self):
        """Se ejecuta cuando el análisis está completo."""
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        self.clean_button.set_sensitive(True)
        
        # Formatear el tamaño total
        size_str = self.format_size(self.total_size)
        self.status_label.set_text(_("Análisis completo. Se pueden liberar: {}").format(size_str))
        
        return False

    def analysis_error(self, error_msg):
        """Se ejecuta si hay un error en el análisis."""
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        self.status_label.set_text(_(f"Error en el análisis: {error_msg}"))
        return False

    def format_size(self, size_bytes):
        """Formatea el tamaño en bytes a una representación legible."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def on_clean_clicked(self, button):
        """Inicia el proceso de limpieza."""
        # Confirmar la limpieza
        dialog = Adw.AlertDialog(
            heading=_("Autorízame y yo limpio el sistema"),
            body=_("Voy a limpiar el sistema.\n\nLiberaré aproximadamente: {}\n\nTen en cuenta que esta acción no se puede revertir.").format(self.format_size(self.total_size))
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("clean", _("Limpiar"))
        dialog.set_response_appearance("clean", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        
        dialog.choose(self, None, self._on_clean_dialog_response, None)

    def _on_clean_dialog_response(self, dialog, result, data):
        """Respuesta del diálogo de confirmación de limpieza."""
        try:
            response = dialog.choose_finish(result)
            if response == "clean":
                self.start_cleanup()
        except Exception as e:
            print(f"Dialog error: {e}")

    def start_cleanup(self):
        """Inicia el proceso de limpieza."""
        self.analyze_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Limpiando archivos..."))
        
        thread = threading.Thread(target=self.perform_cleanup)
        thread.daemon = True
        thread.start()

    def perform_cleanup(self):
        """Realiza la limpieza en un hilo separado."""
        try:
            cleaned_size = 0
            
            # Limpiar directorios seleccionados
            selected_dirs = [d for d, check in self.directory_checks.items() if check.get_active()]
            total_operations = len(selected_dirs) + (1 if self.orphan_check.get_active() else 0) + (1 if self.apt_check.get_active() else 0)
            current_op = 0
            
            for directory in selected_dirs:
                GLib.idle_add(self.update_progress, current_op / total_operations)
                cleaned_size += self.clean_directory(directory)
                current_op += 1
            
            # Limpiar paquetes huérfanos
            if self.orphan_check.get_active():
                GLib.idle_add(self.update_progress, current_op / total_operations)
                self.clean_orphan_packages()
                current_op += 1
            
            # Limpiar caché de paquetes
            if self.apt_check.get_active():
                GLib.idle_add(self.update_progress, current_op / total_operations)
                self.clean_package_cache()
                current_op += 1
            
            GLib.idle_add(self.cleanup_complete, cleaned_size)
            
        except Exception as e:
            print(f"Error en limpieza: {e}")
            GLib.idle_add(self.cleanup_error, str(e))

    def clean_directory(self, directory):
        """Limpia un directorio específico."""
        import shutil
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
                        # Para directorios importantes, solo limpiar el contenido
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
            subprocess.run(pkg_manager.autoremove(), 
                         timeout=300, capture_output=True)
        except Exception as e:
            print(f"Error limpiando paquetes huérfanos: {e}")

    def clean_package_cache(self):
        """Limpia el caché de paquetes."""
        try:
            subprocess.run(pkg_manager.clean_cache(), 
                         timeout=300, capture_output=True)
        except Exception as e:
            print(f"Error limpiando caché de paquetes: {e}")

    def cleanup_complete(self, cleaned_size):
        """Se ejecuta cuando la limpieza está completa."""
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        self.clean_button.set_sensitive(False)
        
        size_str = self.format_size(cleaned_size)
        self.status_label.set_text(_("Limpieza completada. Espacio liberado: {}").format(size_str))
        
        # Mostrar diálogo de completado
        dialog = Adw.AlertDialog(
            heading=_("¡Ya he terminado!"),
            body=_("He dejado impoluto tu Linux.\n\nHe liberado {} que estaban ocupando espacio sin necesidad.").format(size_str)
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        
        return False

    def cleanup_error(self, error_msg):
        """Se ejecuta si hay un error en la limpieza."""
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        self.clean_button.set_sensitive(True)
        self.status_label.set_text(_("Error en la limpieza: {}").format(error_msg))
        
        dialog = Adw.AlertDialog(
            heading=_("Error en la limpieza"),
            body=_("Ocurrió un error durante la limpieza:\n\n{}").format(error_msg)
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        
        return False

class AntivirusWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__()
        self.set_title(_("Análisis antivirus"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(650, 600, 0.85)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Análisis de virus")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Crear scrolled window para el contenido principal si la ventana es muy alta
        if height > 500:  # Solo agregar scroll si la ventana es alta
            scrolled_main = Gtk.ScrolledWindow()
            scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled_main.set_propagate_natural_height(True)
            toolbar_view.set_content(scrolled_main)

            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            scrolled_main.set_child(main_box)
        else:
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            toolbar_view.set_content(main_box)

        # Título y descripción
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        title_box.prepend(icon)
        
        title_label = Gtk.Label(label=_("Puedo analizar tu sistema en busca de virus."))
        title_label.add_css_class("title-label")
        title_box.append(title_label)
        main_box.append(title_box)
        
        desc_label = Gtk.Label(label=_("Protege tu sistema con análisis antivirus"))
        desc_label.add_css_class("subtitle-label")
        main_box.append(desc_label)

        # Estado de ClamAV
        status_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_section.add_css_class("card")
        
        status_title = Gtk.Label(label=_("Estado del antivirus"))
        status_title.add_css_class("title-label")
        status_section.append(status_title)

        self.clam_status_label = Gtk.Label(label=_("Verificando ClamAV..."))
        self.clam_status_label.add_css_class("subtitle-label")
        status_section.append(self.clam_status_label)

        # Botón para instalar/actualizar ClamAV
        self.install_clam_button = Gtk.Button()
        install_clam_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_clam_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        install_clam_box.prepend(install_clam_icon)
        install_clam_label = Gtk.Label(label=_("Instalar ClamAV"))
        install_clam_box.append(install_clam_label)
        self.install_clam_button.set_child(install_clam_box)
        self.install_clam_button.add_css_class("action-button")
        self.install_clam_button.connect("clicked", self.on_install_clam_clicked)
        self.install_clam_button.set_visible(False)
        status_section.append(self.install_clam_button)

        main_box.append(status_section)

        # Sección de configuración del análisis
        config_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        config_section.add_css_class("card")
        
        config_title = Gtk.Label(label=_("Configuración del análisis"))
        config_title.add_css_class("title-label")
        config_section.append(config_title)

        # Tipo de análisis
        scan_type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        scan_type_label = Gtk.Label(label=_("Tipo de análisis:"), xalign=0)
        scan_type_label.add_css_class("title-label")
        scan_type_box.append(scan_type_label)

        # Radio buttons para tipo de análisis
        self.quick_scan_radio = Gtk.CheckButton()
        self.quick_scan_radio.set_active(True)
        quick_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quick_box.prepend(self.quick_scan_radio)
        quick_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        quick_title = Gtk.Label(label=_("Análisis rápido"), xalign=0)
        quick_title.add_css_class("title-label")
        quick_info.append(quick_title)
        quick_desc = Gtk.Label(label=_("Carpetas importantes del usuario (~, /tmp, /var/tmp)"), xalign=0)
        quick_desc.add_css_class("subtitle-label")
        quick_info.append(quick_desc)
        quick_box.append(quick_info)
        scan_type_box.append(quick_box)

        self.full_scan_radio = Gtk.CheckButton()
        self.full_scan_radio.set_group(self.quick_scan_radio)
        full_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        full_box.prepend(self.full_scan_radio)
        full_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        full_title = Gtk.Label(label=_("Análisis completo"), xalign=0)
        full_title.add_css_class("title-label")
        full_info.append(full_title)
        full_desc = Gtk.Label(label=_("Todo el sistema (puedo estar bastante rato trabajando)"), xalign=0)
        full_desc.add_css_class("subtitle-label")
        full_info.append(full_desc)
        full_box.append(full_info)
        scan_type_box.append(full_box)

        self.custom_scan_radio = Gtk.CheckButton()
        self.custom_scan_radio.set_group(self.quick_scan_radio)
        custom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        custom_box.prepend(self.custom_scan_radio)
        custom_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        custom_title = Gtk.Label(label=_("Análisis personalizado"), xalign=0)
        custom_title.add_css_class("title-label")
        custom_info.append(custom_title)
        custom_desc = Gtk.Label(label=_("Selecciona los directorios que quieres que analice"), xalign=0)
        custom_desc.add_css_class("subtitle-label")
        custom_info.append(custom_desc)
        custom_box.append(custom_info)
        scan_type_box.append(custom_box)

        config_section.append(scan_type_box)

        # Directorio personalizado
        self.custom_dir_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.custom_dir_entry = Gtk.Entry()
        self.custom_dir_entry.set_placeholder_text(_("Ruta del directorio a analizar..."))
        self.custom_dir_entry.set_text(os.path.expanduser("~"))
        self.custom_dir_box.append(self.custom_dir_entry)
        
        browse_button = Gtk.Button()
        browse_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        browse_button.set_child(browse_icon)
        browse_button.connect("clicked", self.on_browse_clicked)
        self.custom_dir_box.append(browse_button)
        
        self.custom_dir_box.set_sensitive(False)
        config_section.append(self.custom_dir_box)

        # Conectar señales para habilitar/deshabilitar entrada personalizada
        self.custom_scan_radio.connect("toggled", self.on_custom_toggled)

        main_box.append(config_section)

        # Sección de opciones avanzadas
        advanced_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        advanced_section.add_css_class("card")
        
        adv_title = Gtk.Label(label=_("Opciones avanzadas"))
        adv_title.add_css_class("title-label")
        advanced_section.append(adv_title)

        # Actualizar definiciones
        self.update_defs_check = Gtk.CheckButton()
        self.update_defs_check.set_active(True)
        update_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        update_box.prepend(self.update_defs_check)
        
        update_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        update_label = Gtk.Label(label=_("Actualizar definiciones antes del análisis"), xalign=0)
        update_label.add_css_class("title-label")
        update_info.append(update_label)
        
        update_desc = Gtk.Label(label=_("Descargar las últimas actualizaciones de definiciones de virus para detectarles mejor"), xalign=0)
        update_desc.add_css_class("subtitle-label")
        update_info.append(update_desc)
        
        update_box.append(update_info)
        advanced_section.append(update_box)

        # Análisis profundo
        self.deep_scan_check = Gtk.CheckButton()
        deep_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        deep_box.prepend(self.deep_scan_check)
        
        deep_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        deep_label = Gtk.Label(label=_("Análisis profundo"), xalign=0)
        deep_label.add_css_class("title-label")
        deep_info.append(deep_label)
        
        deep_desc = Gtk.Label(label=_("Incluir archivos comprimidos y análisis heurístico"), xalign=0)
        deep_desc.add_css_class("subtitle-label")
        deep_info.append(deep_desc)
        
        deep_box.append(deep_info)
        advanced_section.append(deep_box)

        main_box.append(advanced_section)

        # Botones de acción
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_margin_top(16)
        
        # Botón actualizar definiciones
        self.update_button = Gtk.Button()
        update_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        update_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        update_box.prepend(update_icon)
        update_label = Gtk.Label(label=_("Actualizar"))
        update_box.append(update_label)
        self.update_button.set_child(update_box)
        self.update_button.add_css_class("secondary-button")
        self.update_button.connect("clicked", self.on_update_clicked)
        button_box.append(self.update_button)
        
        # Botón iniciar análisis
        self.scan_button = Gtk.Button()
        scan_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scan_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        scan_box.prepend(scan_icon)
        scan_label = Gtk.Label(label=_("Iniciar análisis"))
        scan_box.append(scan_label)
        self.scan_button.set_child(scan_box)
        self.scan_button.add_css_class("action-button")
        self.scan_button.connect("clicked", self.on_scan_clicked)
        button_box.append(self.scan_button)

        main_box.append(button_box)

        # Barra de progreso
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_bar.set_visible(False)
        main_box.append(self.progress_bar)

        # Etiqueta de estado
        self.status_label = Gtk.Label(label=_("Listo para iniciar análisis"))
        self.status_label.add_css_class("status-label")
        main_box.append(self.status_label)

        # Área de resultados (scrollable)
        results_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        results_section.add_css_class("card")
        
        results_title = Gtk.Label(label=_("Resultados del análisis"))
        results_title.add_css_class("title-label")
        results_section.append(results_title)

        scrolled_results = Gtk.ScrolledWindow()
        scrolled_results.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_results.set_min_content_height(150)
        
        self.results_text = Gtk.TextView()
        self.results_text.set_editable(False)
        self.results_text.set_monospace(True)
        scrolled_results.set_child(self.results_text)
        
        results_section.append(scrolled_results)
        main_box.append(results_section)

        # Variables de estado
        self.is_clam_installed = False
        self.scan_process = None
        
        # Verificar ClamAV al iniciar
        GLib.timeout_add(500, self.check_clamav_status)

    def check_clamav_status(self):
        """Verifica si ClamAV está instalado."""
        thread = threading.Thread(target=self.check_clam_thread)
        thread.daemon = True
        thread.start()
        return False

    def check_clam_thread(self):
        """Verifica ClamAV en hilo separado."""
        try:
            # Verificar si clamscan está disponible
            result = subprocess.run(['which', 'clamscan'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                # ClamAV está instalado, verificar versión
                version_result = subprocess.run(['clamscan', '--version'], 
                                              capture_output=True, text=True, timeout=10)
                if version_result.returncode == 0:
                    version = version_result.stdout.strip()
                    GLib.idle_add(self.clam_found, version)
                else:
                    GLib.idle_add(self.clam_not_found)
            else:
                GLib.idle_add(self.clam_not_found)
                
        except Exception as e:
            print(f"Error verificando ClamAV: {e}")
            GLib.idle_add(self.clam_not_found)

    def clam_found(self, version):
        """Se ejecuta cuando ClamAV está instalado."""
        self.is_clam_installed = True
        self.clam_status_label.set_text(f"✅ ClamAV instalado: {version}")
        self.install_clam_button.set_visible(False)
        self.scan_button.set_sensitive(True)
        self.update_button.set_sensitive(True)
        return False

    def clam_not_found(self):
        """Se ejecuta cuando ClamAV no está instalado."""
        self.is_clam_installed = False
        self.clam_status_label.set_text("❌ ClamAV no está instalado")
        self.install_clam_button.set_visible(True)
        self.scan_button.set_sensitive(False)
        self.update_button.set_sensitive(False)
        return False

    def on_custom_toggled(self, button):
        """Habilita/deshabilita la entrada de directorio personalizado."""
        self.custom_dir_box.set_sensitive(self.custom_scan_radio.get_active())

    def on_browse_clicked(self, button):
        """Abre un diálogo para seleccionar directorio."""
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar directorio para análisis"),
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Seleccionar"),
            cancel_label=_("Cancelar")
        )
        dialog.connect("response", self._on_folder_dialog_response)
        dialog.show()

    def _on_folder_dialog_response(self, dialog, response):
        """Maneja la respuesta del diálogo de selección de carpeta."""
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.custom_dir_entry.set_text(file.get_path())
        dialog.destroy()

    def on_install_clam_clicked(self, button):
        """Instala ClamAV."""
        dialog = Adw.AlertDialog(
            heading=_("Instalar ClamAV"),
            body=_("¿Quieres instalar ClamAV y sus definiciones de virus?\n\nEsto puede tardar varios minutos y requiere conexión a internet.")
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("install", _("Instalar"))
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")
        
        dialog.choose(self, None, self._on_install_clam_response, None)

    def _on_install_clam_response(self, dialog, result, data):
        """Respuesta del diálogo de instalación de ClamAV."""
        try:
            response = dialog.choose_finish(result)
            if response == "install":
                self.install_clamav()
        except Exception as e:
            print(f"Dialog error: {e}")

    def install_clamav(self):
        """Instala ClamAV."""
        self.install_clam_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Instalando ClamAV..."))
        
        thread = threading.Thread(target=self.install_clam_thread)
        thread.daemon = True
        thread.start()

    def install_clam_thread(self):
        """Instala ClamAV en hilo separado."""
        try:
            # Primero intentar corregir dependencias rotas
            GLib.idle_add(self.update_status_clam, "Corrigiendo dependencias...")
            fix_process = subprocess.Popen(pkg_manager.fix_broken(),
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = fix_process.stdout.readline()
                if output == '' and fix_process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_install_progress)
            
            fix_process.communicate()
            
            # Actualizar repositorios
            GLib.idle_add(self.update_status_clam, "Actualizando repositorios...")
            update_process = subprocess.Popen(pkg_manager.update_cache(),
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            update_process.communicate()
            
            # Instalar ClamAV
            GLib.idle_add(self.update_status_clam, "Instalando ClamAV...")
            install_process = subprocess.Popen(pkg_manager.install_clamav(),
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = install_process.stdout.readline()
                if output == '' and install_process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_install_progress)
            
            _, stderr = install_process.communicate()
            
            if install_process.returncode == 0:
                GLib.idle_add(self.install_clam_complete, True)
            else:
                # Si falla, intentar una vez más con autoremove y fix
                GLib.idle_add(self.update_status_clam, "Reintentando instalación...")
                
                # Limpiar paquetes huérfanos
                subprocess.run(pkg_manager.autoremove(), 
                             capture_output=True, timeout=120)
                
                # Intentar instalar de nuevo
                # Note: install_clamav() doesn't have --fix-missing, but it's a good fallback
                retry_process = subprocess.Popen(pkg_manager.install_clamav(),
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                while True:
                    output = retry_process.stdout.readline()
                    if output == '' and retry_process.poll() is not None:
                        break
                    if output:
                        GLib.idle_add(self.update_install_progress)
                
                _, retry_stderr = retry_process.communicate()
                
                if retry_process.returncode == 0:
                    GLib.idle_add(self.install_clam_complete, True)
                else:
                    GLib.idle_add(self.install_clam_complete, False, f"Error original: {stderr}\nError reintento: {retry_stderr}")
                
        except Exception as e:
            GLib.idle_add(self.install_clam_complete, False, str(e))

    def update_status_clam(self, message):
        """Actualiza el mensaje de estado durante la instalación."""
        self.status_label.set_text(message)
        return False

    def update_install_progress(self):
        """Actualiza la barra de progreso de instalación."""
        current = self.progress_bar.get_fraction()
        new_value = min(1.0, current + 0.02)
        self.progress_bar.set_fraction(new_value)
        return False

    def install_clam_complete(self, success, error_msg=""):
        """Se ejecuta cuando la instalación de ClamAV termina."""
        self.progress_bar.set_visible(False)
        self.install_clam_button.set_sensitive(True)
        
        if success:
            self.status_label.set_text(_("ClamAV instalado correctamente"))
            # Volver a verificar el estado
            GLib.timeout_add(1000, self.check_clamav_status)
        else:
            self.status_label.set_text(_(f"Error instalando ClamAV: {error_msg}"))
            
        return False

    def on_update_clicked(self, button):
        """Actualiza las definiciones de virus."""
        self.update_button.set_sensitive(False)
        self.scan_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Actualizando definiciones de virus..."))
        
        thread = threading.Thread(target=self.update_definitions_thread)
        thread.daemon = True
        thread.start()

    def update_definitions_thread(self):
        """Actualiza las definiciones en hilo separado."""
        try:
            process = subprocess.Popen(['pkexec', 'freshclam'],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_definitions_progress)
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                GLib.idle_add(self.update_definitions_complete, True)
            else:
                GLib.idle_add(self.update_definitions_complete, False, stderr)
                
        except Exception as e:
            GLib.idle_add(self.update_definitions_complete, False, str(e))

    def update_definitions_progress(self):
        """Actualiza el progreso de actualización de definiciones."""
        current = self.progress_bar.get_fraction()
        new_value = min(1.0, current + 0.05)
        self.progress_bar.set_fraction(new_value)
        return False

    def update_definitions_complete(self, success, error_msg=""):
        """Se ejecuta cuando la actualización de definiciones termina."""
        self.progress_bar.set_visible(False)
        self.update_button.set_sensitive(True)
        self.scan_button.set_sensitive(True)
        
        if success:
            self.status_label.set_text(_("Definiciones actualizadas correctamente"))
        else:
            self.status_label.set_text(_(f"Error actualizando definiciones: {error_msg}"))
            
        return False

    def on_scan_clicked(self, button):
        """Inicia el análisis antivirus."""
        # Actualizar definiciones si está marcado
        if self.update_defs_check.get_active():
            self.on_update_clicked(button)
            # Esperar un momento y luego iniciar el análisis
            GLib.timeout_add(2000, self.start_scan_after_update)
        else:
            self.start_scan()

    def start_scan_after_update(self):
        """Inicia el análisis después de actualizar definiciones."""
        if not self.progress_bar.get_visible():  # Esperar a que termine la actualización
            self.start_scan()
            return False
        return True  # Continuar esperando

    def start_scan(self):
        """Inicia el análisis antivirus."""
        self.scan_button.set_sensitive(False)
        self.update_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Iniciando análisis antivirus..."))
        
        # Limpiar resultados anteriores
        buffer = self.results_text.get_buffer()
        buffer.set_text("")
        
        thread = threading.Thread(target=self.scan_thread)
        thread.daemon = True
        thread.start()

    def scan_thread(self):
        """Ejecuta el análisis antivirus en hilo separado."""
        try:
            # Determinar qué analizar
            if self.quick_scan_radio.get_active():
                scan_paths = [os.path.expanduser("~"), "/tmp", "/var/tmp"]
            elif self.full_scan_radio.get_active():
                scan_paths = ["/"]
            else:  # custom scan
                scan_paths = [self.custom_dir_entry.get_text()]
            
            # Construir comando clamscan
            cmd = ['clamscan', '-r', '--no-summary']
            
            if self.deep_scan_check.get_active():
                cmd.extend(['--scan-archive', '--heuristic-scan-precedence'])
            
            cmd.extend(scan_paths)
            
            GLib.idle_add(self.append_result, f"Ejecutando: {' '.join(cmd)}\n\n")
            
            self.scan_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, 
                                               stderr=subprocess.PIPE, universal_newlines=True)
            
            infected_files = []
            scanned_files = 0
            
            while True:
                output = self.scan_process.stdout.readline()
                if output == '' and self.scan_process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    scanned_files += 1
                    
                    # Actualizar progreso cada 100 archivos
                    if scanned_files % 100 == 0:
                        GLib.idle_add(self.update_scan_progress)
                    
                    # Mostrar archivos infectados
                    if "FOUND" in line:
                        infected_files.append(line)
                        GLib.idle_add(self.append_result, f"🦠 INFECTADO: {line}\n")
                    elif scanned_files % 1000 == 0:  # Mostrar progreso cada 1000 archivos
                        GLib.idle_add(self.append_result, f"Analizados: {scanned_files} archivos...\n")
            
            _, stderr = self.scan_process.communicate()
            
            GLib.idle_add(self.scan_complete, len(infected_files), scanned_files, stderr)
            
        except Exception as e:
            GLib.idle_add(self.scan_error, str(e))

    def update_scan_progress(self):
        """Actualiza el progreso del análisis."""
        current = self.progress_bar.get_fraction()
        # Progreso más lento para análisis largos
        new_value = min(0.95, current + 0.01)
        self.progress_bar.set_fraction(new_value)
        return False

    def append_result(self, text):
        """Añade texto a los resultados."""
        buffer = self.results_text.get_buffer()
        end_iter = buffer.get_end_iter()
        buffer.insert(end_iter, text)
        
        # Scroll hacia abajo
        mark = buffer.get_insert()
        self.results_text.scroll_to_mark(mark, 0.0, False, 0.0, 0.0)
        return False

    def scan_complete(self, infected_count, scanned_count, stderr):
        """Se ejecuta cuando el análisis termina."""
        self.progress_bar.set_fraction(1.0)
        self.scan_button.set_sensitive(True)
        self.update_button.set_sensitive(True)
        
        if infected_count == 0:
            status = f"✅ Análisis completado. He revisado {scanned_count} archivos y no he encontrado amenazas. Puedes estar tranquilo."
            GLib.idle_add(self.append_result, f"\n{status}\n")
        else:
            status = f"⚠️ ¡Cuidado! He pillado amenazas que puede que te la estén liando... He encontrado {infected_count} amenazas en {scanned_count} archivos analizados. Para evitar problemas toma medidas. Recomendamos realizar una reinstalación siempre que se encuentren virus."
            GLib.idle_add(self.append_result, f"\n{status}\n")
            
            # Mostrar diálogo con opciones de limpieza
            self.show_threat_dialog(infected_count)
        
        self.status_label.set_text(status)
        
        GLib.timeout_add(2000, self.hide_progress_bar)
        return False

    def hide_progress_bar(self):
        """Oculta la barra de progreso."""
        self.progress_bar.set_visible(False)
        return False

    def show_threat_dialog(self, threat_count):
        """Muestra diálogo cuando se encuentran amenazas."""
        dialog = Adw.AlertDialog(
            heading=_("⚠️ ¡Cuidado!"),
            body=_(f"He detectado {threat_count} amenazas en tu sistema.\n\n¿Qué quieres hacer?")
        )
        dialog.add_response("ignore", _("Ignorar"))
        dialog.add_response("quarantine", _("Poner en cuarentena"))
        dialog.add_response("delete", _("Eliminar amenazas"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("quarantine", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("quarantine")
        dialog.set_close_response("ignore")
        
        dialog.choose(self, None, self._on_threat_dialog_response, None)

    def _on_threat_dialog_response(self, dialog, result, data):
        """Respuesta del diálogo de amenazas."""
        try:
            response = dialog.choose_finish(result)
            if response == "quarantine":
                self.append_result("\n🔒 Poniendo amenazas en cuarentena...\n")
                # Aquí se implementaría la cuarentena
                self.append_result("Funcionalidad de cuarentena no implementada aún.\n")
            elif response == "delete":
                self.append_result("\n🗑️ Eliminando amenazas...\n")
                # Aquí se implementaría la eliminación
                self.append_result("Funcionalidad de eliminación no implementada aún.\n")
        except Exception as e:
            print(f"Dialog error: {e}")

    def scan_error(self, error_msg):
        """Se ejecuta si hay un error en el análisis."""
        self.progress_bar.set_visible(False)
        self.scan_button.set_sensitive(True)
        self.update_button.set_sensitive(True)
        self.status_label.set_text(_(f"Error en el análisis: {error_msg}"))
        GLib.idle_add(self.append_result, f"\n❌ Error: {error_msg}\n")
        return False

class UninstallationProgressWindow(Adw.Window):
    def __init__(self, parent, message):
        super().__init__()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(300, 300)
        
        # Contenedor principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_margin_top(40)
        main_box.set_margin_bottom(40)
        main_box.set_margin_start(40)
        main_box.set_margin_end(40)
        
        # Spinner grande
        spinner = Gtk.Spinner()
        spinner.set_size_request(80, 80)
        spinner.start()
        main_box.append(spinner)
        
        # Texto de estado
        self.label = Gtk.Label(label=message)
        self.label.add_css_class("title-label")
        self.label.set_wrap(True)
        self.label.set_max_width_chars(25)
        self.label.set_justify(Gtk.Justification.CENTER)
        main_box.append(self.label)
        
        self.set_content(main_box)

class InstalledAppsWindow(Adw.Window):
    def __init__(self, parent):
        super().__init__()
        self.set_title("Aplicaciones instaladas")
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(500, 400, 0.7)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Aplicaciones instaladas")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Contenido desplazable para pantallas pequeñas
        if height > 380:
            scrolled_main = Gtk.ScrolledWindow()
            scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled_main.set_propagate_natural_height(True)
            toolbar_view.set_content(scrolled_main)

            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            scrolled_main.set_child(main_box)
        else:
            main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            main_box.set_margin_top(16)
            main_box.set_margin_bottom(16)
            main_box.set_margin_start(16)
            main_box.set_margin_end(16)
            toolbar_view.set_content(main_box)

        # Barra de búsqueda con spinner indicador
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search_box.set_margin_start(8)
        search_box.set_margin_end(8)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text(_("Buscar aplicaciones..."))
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.search_entry.add_css_class("search-entry")
        self.search_entry.set_hexpand(True)
        search_box.append(self.search_entry)
        
        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(24, 24)
        search_box.append(self.search_spinner)
        
        main_box.append(search_box)
        
        self.is_loading = False

        # Contenedor para el contenido (Stack para manejar estados)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        # Quitamos la clase "card" para evitar el recuadro anidado
        main_box.append(content_box)

        # Separador sutil
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        separator.set_margin_bottom(8)
        content_box.append(separator)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        content_box.append(self.stack)

        # 1. Estado de Carga (Spinner)
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_margin_top(40)
        loading_box.set_margin_bottom(40)
        
        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        loading_box.append(spinner)
        
        self.loading_label = Gtk.Label(label=_("Cargando aplicaciones..."))
        self.loading_label.add_css_class("subtitle-label")
        loading_box.append(self.loading_label)
        
        self.stack.add_named(loading_box, "loading")

        # 2. Estado de Lista (ScrolledWindow + ListBox)
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(300)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_filter_func(self.filter_func)
        scrolled_window.set_child(self.listbox)
        
        self.stack.add_named(scrolled_window, "list")

        # 3. Estado "No encontrado"
        no_results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        no_results_box.set_valign(Gtk.Align.CENTER)
        no_results_box.set_halign(Gtk.Align.CENTER)
        no_results_box.set_margin_top(40)
        no_results_box.set_margin_bottom(40)
        
        no_results_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        no_results_icon.set_pixel_size(48)
        no_results_box.append(no_results_icon)
        
        self.no_results_label = Gtk.Label(label=_("No he encontrado nada que coincida"))
        self.no_results_label.add_css_class("title-label")
        no_results_box.append(self.no_results_label)
        
        self.stack.add_named(no_results_box, "empty")
        
        # Barra de progreso para desinstalación
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_bar.set_visible(False)
        main_box.append(self.progress_bar)

        # Mensaje de estado
        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("status-label")
        main_box.append(self.status_label)
        
        # Cargar aplicaciones
        self.load_installed_apps()
    
    def load_installed_apps(self):
        # Limpiar la lista actual
        child = self.listbox.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child
            
        # Mostrar estado de carga e iniciar spinner de búsqueda
        self.is_loading = True
        self.search_spinner.start()
        self.loading_label.set_text(_("Cargando aplicaciones..."))
        self.stack.set_visible_child_name("loading")
        
        # Iniciar un hilo para cargar las aplicaciones
        thread = threading.Thread(target=self.load_apps_thread)
        thread.daemon = True
        thread.start()
    
    def load_apps_thread(self):
        try:
            # Obtener paquetes instalados
            packages = []
            appimages = []
            brew_packages = []
            
            # Obtener paquetes del sistema
            try:
                packages = pkg_manager.list_installed()
            except Exception as e:
                print(f"Error al obtener paquetes: {e}")
            
            # Obtener paquetes de Homebrew
            if HAS_BREW:
                print(f"DEBUG: Intentando listar paquetes de Homebrew usando {BREW_PATH}")
                try:
                    # Listar fórmulas y casks
                    output = subprocess.check_output([BREW_PATH, 'list', '--formula'], 
                                                   timeout=15, stderr=subprocess.STDOUT).decode('utf-8')
                    formulas = [line.strip() for line in output.split('\n') if line.strip()]
                    brew_packages.extend(formulas)
                    print(f"DEBUG: Encontradas {len(formulas)} fórmulas de Homebrew")
                    
                    output_cask = subprocess.check_output([BREW_PATH, 'list', '--cask'], 
                                                        timeout=15, stderr=subprocess.STDOUT).decode('utf-8')
                    casks = [line.strip() for line in output_cask.split('\n') if line.strip()]
                    brew_packages.extend(casks)
                    print(f"DEBUG: Encontrados {len(casks)} casks de Homebrew")
                except Exception as e:
                    print(f"DEBUG: Error al obtener paquetes de Homebrew: {e}")
            else:
                print("DEBUG: Homebrew no detectado (HAS_BREW es False)")

            # Obtener AppImages y PWAs
            pwas = []
            desktop_dir = "/usr/share/applications"
            if os.path.exists(desktop_dir):
                for filename in os.listdir(desktop_dir):
                    if filename.endswith(".desktop"):
                        desktop_path = os.path.join(desktop_dir, filename)
                        try:
                            with open(desktop_path, 'r') as f:
                                content = f.read()
                                app_name = filename.replace(".desktop", "")

                                # Detectar si es de AppInstall:
                                # 1. Tiene la marca nueva (AppImage o PWA)
                                # 2. Tiene el icono por defecto antiguo
                                # 3. Tiene el patrón de ruta de binario e icono personalizado de AppInstall
                                if "X-AppInstall=PWA" in content:
                                    pwas.append(app_name)
                                else:
                                    is_appinstall_app = (
                                        "X-AppInstall=AppImage" in content or 
                                        ("/usr/bin/" in content and "appimage.png" in content) or
                                        (f"Exec=/usr/bin/{app_name}" in content and f"Icon=/usr/share/pixmaps/{app_name}" in content)
                                    )

                                    if is_appinstall_app:
                                        appimages.append(app_name)
                        except:
                            pass
            
            # Preparar la lista completa una sola vez
            all_apps = []
            for pw in pwas: all_apps.append((pw, "pwa"))
            for a in appimages: all_apps.append((a, "appimage"))
            for b in brew_packages: all_apps.append((b, "brew"))
            for p in packages: all_apps.append((p, "system"))

            # Actualizar la UI en lotes para evitar sobrecargar el bucle principal
            def update_ui_batch(index):
                if not all_apps:
                    self.is_loading = False
                    self.search_spinner.stop()
                    self.stack.set_visible_child_name("empty")
                    return False

                # Mostrar la lista desde el primer lote para que el usuario vea progreso
                if index == 0:
                    self.stack.set_visible_child_name("list")

                batch_size = 50 # Aumentamos un poco el lote para mayor rapidez
                end_index = min(index + batch_size, len(all_apps))
                
                for i in range(index, end_index):
                    name, type = all_apps[i]
                    self.add_app_to_list(name, type == "appimage", type == "brew", type == "pwa")
                
                # Si hay texto de búsqueda, invalidar el filtro para que se aplique a los nuevos elementos
                if self.search_entry.get_text():
                    self.on_search_changed(self.search_entry)

                if end_index < len(all_apps):
                    # Programar el siguiente lote
                    GLib.idle_add(lambda: update_ui_batch(end_index))
                else:
                    # Finalizado
                    self.is_loading = False
                    self.search_spinner.stop()
                    # Forzar el filtrado final y verificar resultados
                    self.on_search_changed(self.search_entry)
                
                return False
            
            # Programar la actualización de la UI en el hilo principal
            GLib.idle_add(lambda: update_ui_batch(0))
            
        except Exception as e:
            print(f"Error al cargar aplicaciones: {e}")
            GLib.idle_add(self.show_error_message)
    
    def add_app_to_list(self, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        """Añadir una aplicación a la lista"""
        row = Gtk.ListBoxRow()
        row.add_css_class("list-row")
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_margin_top(8)
        hbox.set_margin_bottom(8)
        hbox.set_margin_start(8)
        hbox.set_margin_end(8)
        row.set_child(hbox)
        
        # Icono para el tipo de aplicación
        if is_appimage:
            icon = Gtk.Image.new_from_icon_name("application-x-executable")
        elif is_pwa:
            icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        elif is_brew:
            # Intentar cargar el logo de Homebrew
            brew_logo_path = os.path.expanduser("~/.cache/appinstall/homebrew_logo.png")
            if not os.path.exists(brew_logo_path):
                # Descargar el logo si no existe
                try:
                    os.makedirs(os.path.dirname(brew_logo_path), exist_ok=True)
                    response = requests.get("https://upload.wikimedia.org/wikipedia/commons/3/34/Homebrew_logo.png", timeout=10)
                    if response.status_code == 200:
                        with open(brew_logo_path, 'wb') as f:
                            f.write(response.content)
                except:
                    pass
            
            if os.path.exists(brew_logo_path):
                icon = Gtk.Image.new_from_file(brew_logo_path)
                icon.set_pixel_size(24)
            else:
                icon = Gtk.Image.new_from_icon_name("system-software-install")
        else:
            icon = Gtk.Image.new_from_icon_name("package-x-generic")
            
        hbox.prepend(icon)
        
        # Nombre a mostrar
        display_name = package_name
        
        # Contenedor vertical para nombre y tipo
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_hexpand(True) # Expandir para empujar el botón al final
        
        label = Gtk.Label(label=display_name, xalign=0)
        label.add_css_class("title-label")
        vbox.append(label)
        
        # Etiqueta para el tipo
        if is_appimage:
            type_text = _("AppImage")
        elif is_pwa:
            type_text = _("PWA (Web App)")
        elif is_brew:
            type_text = _("Paquete Homebrew")
        else:
            type_text = _("Paquete del sistema")
            
        type_label = Gtk.Label(label=type_text, xalign=0)
        type_label.add_css_class("subtitle-label")
        vbox.append(type_label)
        
        hbox.append(vbox)
        
        # Botón de desinstalar con icono
        button = Gtk.Button()
        button.set_tooltip_text(_("Desinstalar"))
        button.add_css_class("destructive-button")
        button.set_valign(Gtk.Align.CENTER) # Centrar verticalmente respecto al texto
        
        button_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        button.set_child(button_icon)
        
        button.connect("clicked", self.on_uninstall_clicked, package_name, is_appimage, is_brew, is_pwa)
        hbox.append(button)
        
        self.listbox.append(row)
    
    # Mensaje de que no hay aplicaciones instaladas en el sistema (clara prueba de que está habiendo un error)
    def show_no_apps_message(self):
        self.is_loading = False
        self.search_spinner.stop()
        
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        
        icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        box.append(icon)
        
        label = Gtk.Label(label=_("No he encontrado aplicaciones instaladas en tu sistema"))
        label.add_css_class("title-label")
        box.append(label)
        
        row.set_child(box)
        self.listbox.append(row)
        self.stack.set_visible_child_name("list")
        return False
    
    def show_error_message(self):
        self.is_loading = False
        self.search_spinner.stop()
        
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        
        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        box.append(icon)
        
        label = Gtk.Label(label=_("No he podido encontrar aplicaciones instaladas en tu sistema"))
        label.add_css_class("title-label")
        box.append(label)
        
        row.set_child(box)
        self.listbox.append(row)
        self.stack.set_visible_child_name("list")
        return False
    
    def on_search_changed(self, entry):
        # Si no estamos cargando inicialmente, mostrar el spinner brevemente para indicar búsqueda activa
        if not self.is_loading:
            self.search_spinner.start()
            
        self.listbox.invalidate_filter()
        # Verificar si hay resultados visibles después de invalidar el filtro
        GLib.idle_add(self.check_filter_results)

    def check_filter_results(self):
        has_visible = False
        child = self.listbox.get_first_child()
        while child:
            if child.is_visible() and child.get_child():
                has_visible = True
                break
            child = child.get_next_sibling()
        
        if not has_visible:
            if self.is_loading:
                self.loading_label.set_text(_("Buscando aplicaciones..."))
                self.stack.set_visible_child_name("loading")
            else:
                self.stack.set_visible_child_name("empty")
                self.search_spinner.stop()
        else:
            self.stack.set_visible_child_name("list")
            if not self.is_loading:
                self.search_spinner.stop()
        return False
    
    def filter_func(self, row):
        text = self.search_entry.get_text().lower()
        if not text:
            return True
        
        # Buscar en el título de la aplicación
        box = row.get_child()
        if box and isinstance(box, Gtk.Box):
            child = box.get_first_child()
            while child:
                if isinstance(child, Gtk.Box) and child.get_orientation() == Gtk.Orientation.VERTICAL:
                    label_child = child.get_first_child()
                    while label_child:
                        if isinstance(label_child, Gtk.Label) and hasattr(label_child, 'get_text'):
                            if text in label_child.get_text().lower():
                                return True
                        label_child = label_child.get_next_sibling()
                child = child.get_next_sibling()
        return False
    
    # Aviso desinstalación
    def on_uninstall_clicked(self, button, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        if is_appimage:
            message = _("¿Deseas desinstalar {}? (AppImage)").format(package_name)
        elif is_pwa:
            message = _("¿Deseas desinstalar {}? (Web App)").format(package_name)
        elif is_brew:
            message = _("¿Deseas desinstalar {}? (Homebrew)").format(package_name)
        else:
            message = _("¿Deseas desinstalar {}?").format(package_name)
            
        dialog = Adw.AlertDialog(
            heading=_("Confirmación"),
            body=message
        )
        dialog.add_response("no", _("No"))
        dialog.add_response("yes", _("Sí"))
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("no")
        dialog.set_close_response("no")
        
        dialog.choose(self, None, self._on_uninstall_dialog_response, (package_name, is_appimage, is_brew, is_pwa))
    
    def _on_uninstall_dialog_response(self, dialog, result, data):
        package_name, is_appimage, is_brew, is_pwa = data
        try:
            response = dialog.choose_finish(result)
            if response == "yes":
                self.uninstall_package(package_name, is_appimage, is_brew, is_pwa)
        except Exception as e:
            print(f"Dialog error: {e}")
    
    # Desinstalar paquete
    def uninstall_package(self, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        self.status_label.set_text(_("Desinstalando {}...").format(package_name))
        
        # Mostrar popup de progreso
        self.uninst_progress_dialog = UninstallationProgressWindow(self, _("Desinstalando {}...").format(package_name))
        self.uninst_progress_dialog.present()

        if is_appimage:
            # Eliminar el AppImage, su archivo .desktop y sus posibles iconos
            cmd = [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/bin/{package_name} && ' +
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.*'
            ]
        elif is_pwa:
            # Eliminar la PWA (solo .desktop e iconos)
            cmd = [
                'pkexec', 'bash', '-c',
                f'rm -f /usr/share/applications/{package_name}.desktop && ' +
                f'rm -f /usr/share/pixmaps/{package_name}.*'
            ]
        elif is_brew:
            # Desinstalar con brew
            cmd = [BREW_PATH, 'uninstall', package_name]
        else:
            # Eliminar un paquete normal usando el gestor del sistema
            cmd = pkg_manager.uninstall(package_name)

        thread = threading.Thread(target=self.run_uninstall, args=(cmd, package_name, is_appimage, is_brew, is_pwa))

        thread.daemon = True
        thread.start()
    
    def run_uninstall(self, cmd, package_name, is_appimage=False, is_brew=False, is_pwa=False):
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_uninstall_progress)
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                GLib.idle_add(self.uninstall_complete, package_name, True, is_appimage, is_brew, is_pwa)
            else:
                GLib.idle_add(self.uninstall_complete, package_name, False, is_appimage, is_brew, is_pwa, str(stderr))
        except Exception as e:
            GLib.idle_add(self.uninstall_complete, package_name, False, is_appimage, is_brew, is_pwa, str(e))
    
    # Barra de progreso de la desinstalación
    def update_uninstall_progress(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.05)
        self.progress_bar.set_fraction(new_value)
        return False

    # Mensaje después de ejecutar la desinstalación
    def uninstall_complete(self, package_name, success, is_appimage=False, is_brew=False, is_pwa=False, error_message=None):
        # Cerrar popup si existe
        if hasattr(self, 'uninst_progress_dialog') and self.uninst_progress_dialog:
            self.uninst_progress_dialog.close()
            self.uninst_progress_dialog = None

        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        
        if success:
            if is_appimage:
                message = _("{} ha sido desinstalado correctamente. Recuerda borrar los archivos que haya creado la aplicación.").format(package_name)
            elif is_pwa:
                message = _("La Web App {} ha sido eliminada correctamente.").format(package_name)
            elif is_brew:
                message = _("{} ha sido desinstalado de Homebrew correctamente.").format(package_name)
            else:
                message = _("{} ha sido desinstalado correctamente.").format(package_name)
                
            dialog = Adw.AlertDialog(
                heading=_("Desinstalación completada"),
                body=message
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            self.status_label.set_text(_("Desinstalación completada"))
        else:
            if is_appimage:
                message = _("Error al desinstalar AppImage - {}.").format(package_name)
            elif is_pwa:
                message = _("Error al eliminar la Web App {}.").format(package_name)
            elif is_brew:
                message = _("Error al desinstalar {} de Homebrew.").format(package_name)
            else:
                message = _("Error al desinstalar {}.").format(package_name)
                
            dialog = Adw.AlertDialog(
                heading=_("Error en la desinstalación"),
                body=f"{message}\n\n{error_message or ''}"
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            self.status_label.set_text(_("Uy... ha habido un error cuando estaba desinstalándote la app"))
        
        dialog.present(self)
        self.load_installed_apps()  # Refrescar la lista


class PWAConfigWindow(Adw.Window):
    def __init__(self, parent, callback):
        super().__init__()
        self.set_title(_("Crear PWA (Web App)"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(450, 500, 0.8)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")
        
        self.callback = callback
        self.icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appimage.png")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Crear PWA")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        toolbar_view.set_content(main_box)

        # Sección de la URL
        url_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        url_section.add_css_class("card")
        
        url_label = Gtk.Label(label=_("Introduce la URL de la web"), xalign=0)
        url_label.add_css_class("title-label")
        url_section.append(url_label)
        
        url_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text(_("https://ejemplo.com"))
        self.url_entry.set_hexpand(True)
        url_hbox.append(self.url_entry)
        
        fetch_button = Gtk.Button()
        fetch_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        fetch_button.set_child(fetch_icon)
        fetch_button.set_tooltip_text(_("Cargar información de la web"))
        fetch_button.connect("clicked", self.on_fetch_clicked)
        url_hbox.append(fetch_button)
        
        url_section.append(url_hbox)
        main_box.append(url_section)

        # Sección del nombre e icono (inicialmente desactivada o vacía)
        self.info_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.info_section.set_sensitive(False)
        
        # Nombre
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_box.add_css_class("card")
        name_label = Gtk.Label(label=_("Nombre de la aplicación"), xalign=0)
        name_label.add_css_class("title-label")
        name_box.append(name_label)
        self.name_entry = Gtk.Entry()
        name_box.append(self.name_entry)
        self.info_section.append(name_box)
        
        # Icono
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon_box.add_css_class("card")
        icon_label = Gtk.Label(label=_("Icono"), xalign=0)
        icon_label.add_css_class("title-label")
        icon_box.append(icon_label)
        
        icon_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.icon_image = Gtk.Image.new_from_file(self.icon_path)
        self.icon_image.set_pixel_size(64)
        icon_hbox.append(self.icon_image)
        
        change_icon_button = Gtk.Button(label=_("Cambiar icono..."))
        change_icon_button.connect("clicked", self.on_change_icon_clicked)
        change_icon_button.set_valign(Gtk.Align.CENTER)
        icon_hbox.append(change_icon_button)
        icon_box.append(icon_hbox)
        self.info_section.append(icon_box)
        
        main_box.append(self.info_section)

        # Spinner de carga
        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.set_halign(Gtk.Align.CENTER)
        main_box.append(self.spinner)

        # Botones de acción
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(8)
        
        cancel_button = Gtk.Button(label=_("Cancelar"))
        cancel_button.connect("clicked", lambda x: self.close())
        button_box.append(cancel_button)
        
        self.create_button = Gtk.Button()
        self.create_button.add_css_class("action-button")
        create_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        create_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        create_box.prepend(create_icon)
        create_label = Gtk.Label(label=_("¡Crear PWA!"))
        create_box.append(create_label)
        self.create_button.set_child(create_box)
        self.create_button.connect("clicked", self.on_create_clicked)
        self.create_button.set_sensitive(False)
        button_box.append(self.create_button)
        
        main_box.append(button_box)

    def on_fetch_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            return
        
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.url_entry.set_text(url)

        self.spinner.start()
        self.spinner.set_visible(True)
        self.info_section.set_sensitive(False)
        
        thread = threading.Thread(target=self.fetch_info_thread, args=(url,))
        thread.daemon = True
        thread.start()

    def fetch_info_thread(self, url):
        try:
            # Intentar obtener el título de la página
            response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            title = ""
            if response.status_code == 200:
                import re
                match = re.search('<title>(.*?)</title>', response.text, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
            
            if not title:
                # Fallback al dominio
                from urllib.parse import urlparse
                title = urlparse(url).netloc.replace("www.", "")

            # Obtener el favicon usando el servicio de Google (más fiable que parsear HTML)
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
            
            icon_temp_path = os.path.join(os.path.expanduser("~/.cache/appinstall"), f"pwa_{domain}.png")
            os.makedirs(os.path.dirname(icon_temp_path), exist_ok=True)
            
            icon_response = requests.get(favicon_url, timeout=10)
            if icon_response.status_code == 200:
                with open(icon_temp_path, 'wb') as f:
                    f.write(icon_response.content)
                icon_to_use = icon_temp_path
            else:
                icon_to_use = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appimage.png")

            GLib.idle_add(self.on_info_fetched, title, icon_to_use)
        except Exception as e:
            print(f"Error fetching PWA info: {e}")
            GLib.idle_add(self.on_info_fetched, "", self.icon_path)

    def on_info_fetched(self, title, icon_path):
        self.spinner.stop()
        self.spinner.set_visible(False)
        self.info_section.set_sensitive(True)
        self.create_button.set_sensitive(True)
        
        if title:
            self.name_entry.set_text(title)
        
        self.icon_path = icon_path
        self.icon_image.set_from_file(icon_path)
        return False

    def on_change_icon_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar icono para la PWA"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        dialog.connect("response", self._on_icon_dialog_response)
        dialog.show()

    def _on_icon_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.icon_path = file.get_path()
                self.icon_image.set_from_file(self.icon_path)
        dialog.destroy()

    def on_create_clicked(self, button):
        name = self.name_entry.get_text().strip()
        url = self.url_entry.get_text().strip()
        if name and url:
            self.callback(name, url, self.icon_path)
            self.close()


class AppImageConfigWindow(Adw.Window):
    def __init__(self, parent, file_path, callback):
        super().__init__()
        self.set_title(_("Configurar AppImage"))
        
        # Obtener tamaño seguro de ventana
        width, height = get_safe_window_size(450, 400, 0.8)
        self.set_default_size(width, height)
            
        self.set_transient_for(parent)
        self.set_modal(True)
        self.add_css_class("main-window")
        
        self.file_path = file_path
        self.callback = callback
        
        # Nombre por defecto basado en el archivo
        filename = os.path.basename(file_path)
        self.default_name = os.path.splitext(filename)[0]
        
        # Icono por defecto de App Install
        self.icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appimage.png")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Configurar AppImage")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(16)
        main_box.set_margin_end(16)
        toolbar_view.set_content(main_box)

        # Sección del nombre
        name_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_section.add_css_class("card")
        
        name_label = Gtk.Label(label=_("¿Cómo quieres llamar a la app?"), xalign=0)
        name_label.add_css_class("title-label")
        name_section.append(name_label)
        
        self.name_entry = Gtk.Entry()
        self.name_entry.set_text(self.default_name)
        self.name_entry.set_placeholder_text(_("Escribe el nombre de la aplicación..."))
        name_section.append(self.name_entry)
        
        main_box.append(name_section)

        # Sección del icono
        icon_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon_section.add_css_class("card")
        
        icon_title = Gtk.Label(label=_("Ponle un icono chulo"), xalign=0)
        icon_title.add_css_class("title-label")
        icon_section.append(icon_title)
        
        icon_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        
        self.icon_image = Gtk.Image.new_from_file(self.icon_path)
        self.icon_image.set_pixel_size(64)
        icon_hbox.append(self.icon_image)
        
        icon_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        self.icon_label = Gtk.Label(label=_("Icono por defecto"), xalign=0)
        self.icon_label.add_css_class("subtitle-label")
        icon_vbox.append(self.icon_label)
        
        select_icon_button = Gtk.Button()
        select_icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        select_icon_icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        select_icon_box.prepend(select_icon_icon)
        select_icon_text = Gtk.Label(label=_("Seleccionar icono..."))
        select_icon_box.append(select_icon_text)
        select_icon_button.set_child(select_icon_box)
        select_icon_button.connect("clicked", self.on_select_icon_clicked)
        icon_vbox.append(select_icon_button)
        
        icon_hbox.append(icon_vbox)
        icon_section.append(icon_hbox)
        
        main_box.append(icon_section)

        # Botones de acción
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        button_box.set_halign(Gtk.Align.END)
        button_box.set_margin_top(8)
        
        cancel_button = Gtk.Button(label=_("Cancelar"))
        cancel_button.connect("clicked", lambda x: self.close())
        button_box.append(cancel_button)
        
        self.install_button = Gtk.Button()
        self.install_button.add_css_class("action-button")
        install_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        install_box.prepend(install_icon)
        install_label = Gtk.Label(label=_("¡Instalar!"))
        install_box.append(install_label)
        self.install_button.set_child(install_box)
        self.install_button.connect("clicked", self.on_install_clicked)
        button_box.append(self.install_button)
        
        main_box.append(button_box)

    def on_select_icon_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar icono para la aplicación"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        
        filter_img = Gtk.FileFilter()
        filter_img.set_name(_("Archivos de imagen"))
        filter_img.add_mime_type("image/png")
        filter_img.add_mime_type("image/jpeg")
        filter_img.add_mime_type("image/svg+xml")
        dialog.add_filter(filter_img)
        
        dialog.connect("response", self._on_icon_dialog_response)
        dialog.show()

    def _on_icon_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.icon_path = file.get_path()
                self.icon_image.set_from_file(self.icon_path)
                self.icon_label.set_text(os.path.basename(self.icon_path))
        dialog.destroy()

    def on_install_clicked(self, button):
        custom_name = self.name_entry.get_text().strip()
        if not custom_name:
            custom_name = self.default_name
        
        # Llamar al callback del padre para proceder con la instalación
        self.callback(custom_name, self.icon_path)
        self.close()


class PackageInstaller(Adw.ApplicationWindow):
    def __init__(self, app, file_to_open=None):
        super().__init__(application=app)
        self.set_title("App Install")
        
        # El nombre del icono debe coincidir con el archivo es.inled.AppInstall.png
        self.set_icon_name("es.inled.AppInstall")

        # Ajustar tamaño de ventana principal a la pantalla
        width, height = get_safe_window_size(600, 500, 0.9)
        self.set_default_size(width, height)
        self.add_css_class("main-window")
        
        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="App Install", subtitle=_("Versión {}").format(CURRENT_VERSION))
        header_bar.set_title_widget(title_widget)
        header_bar.add_css_class("header-bar")
        
        # Botón de menú en la header bar
        menu_button = Gtk.MenuButton()
        menu_button.set_tooltip_text(_("Menú"))
        icon = Gtk.Image.new_from_icon_name("open-menu-symbolic")
        menu_button.set_child(icon)
        
        # Crear el menú
        popover = Gtk.Popover()
        popover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        popover_box.set_margin_top(10)
        popover_box.set_margin_bottom(10)
        popover_box.set_margin_start(10)
        popover_box.set_margin_end(10)
        
        # Elementos del menú
        about_button = Gtk.Button(label=_("Acerca de App Install"))
        about_button.connect("clicked", self.on_about_clicked)
        popover_box.append(about_button)
        
        report_button = Gtk.Button(label=_("Reportar un error"))
        report_button.connect("clicked", self.on_report_issue)
        popover_box.append(report_button)
        
        update_button = Gtk.Button(label=_("Buscar actualizaciones"))
        update_button.connect("clicked", self.on_check_updates_clicked)
        popover_box.append(update_button)
        
        popover.set_child(popover_box)
        menu_button.set_popover(popover)
        
        header_bar.pack_end(menu_button)
        
        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        self.set_content(toolbar_view)

        # Breakpoint para pantallas pequeñas
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 500px"))
        # El setter con None puede fallar si no se mapea correctamente a GValue
        self.add_breakpoint(breakpoint)

        # Usar Adw.Clamp para que se vea bien en pantallas grandes y pequeñas
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        toolbar_view.set_content(clamp)

        # Contenido principal siempre con scroll
        scrolled_main = Gtk.ScrolledWindow()
        scrolled_main.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_main.set_propagate_natural_height(True)
        clamp.set_child(scrolled_main)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        scrolled_main.set_child(main_box)
        
        # Sección de selección de archivo
        file_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        file_section.add_css_class("card")
        
        # Título de la sección
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        title_box.prepend(icon)
        
        title_label = Gtk.Label(label=_("¿Qué debo instalar?"))
        title_label.add_css_class("title-label")
        title_box.append(title_label)
        
        file_section.append(title_box)
        
        # Selector de archivo con estilo
        file_chooser_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        file_chooser_box.add_css_class("file-chooser-button")
        
        file_icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
        file_chooser_box.append(file_icon)
        
        file_label = Gtk.Label(label=_("Selecciona el archivo que debo instalar"))
        file_label.add_css_class("subtitle-label")
        file_chooser_box.append(file_label)
        
        file_chooser_button = Gtk.Button()
        file_chooser_button.set_child(file_chooser_box)
        file_chooser_button.connect("clicked", self.on_file_chooser_clicked)
        
        file_section.append(file_chooser_button)
        
        # Etiqueta para mostrar el archivo seleccionado
        self.selected_file_label = Gtk.Label(label=_("Aún no has seleccionado ningún archivo"))
        self.selected_file_label.add_css_class("subtitle-label")
        file_section.append(self.selected_file_label)
        
        # Entrada de texto para instalar por nombre (Apt o Brew)
        name_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        name_section.set_margin_top(8)
        
        name_label = Gtk.Label(label=_("O escribe el nombre del paquete"), xalign=0)
        name_label.add_css_class("subtitle-label")
        name_section.append(name_label)
        
        self.package_name_entry = Gtk.Entry()
        self.package_name_entry.set_placeholder_text(_("ej: vlc, firefox, chrome..."))
        self.package_name_entry.connect("changed", self.on_package_name_changed)
        name_section.append(self.package_name_entry)

        # Resultados de búsqueda (ListBox integrado justo debajo de la entrada)
        self.search_results_scrolled = Gtk.ScrolledWindow()
        self.search_results_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.search_results_scrolled.set_min_content_height(100)
        self.search_results_scrolled.set_max_content_height(300)
        self.search_results_scrolled.set_propagate_natural_height(True)
        self.search_results_scrolled.set_visible(False)
        # Quitamos la clase "card" para que no tenga borde propio y se integre en la tarjeta superior
        
        self.search_results_list = Gtk.ListBox()
        self.search_results_list.add_css_class("navigation-sidebar") # Estilo más limpio
        self.search_results_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_results_list.connect("row-activated", self.on_search_result_activated)
        self.search_results_scrolled.set_child(self.search_results_list)
        name_section.append(self.search_results_scrolled)

        # Spinner de búsqueda
        self.search_spinner = Gtk.Spinner()
        self.search_spinner.set_size_request(24, 24)
        self.search_spinner.set_halign(Gtk.Align.CENTER)
        self.search_spinner.set_margin_top(10)
        self.search_spinner.set_visible(False)
        name_section.append(self.search_spinner)

        file_section.append(name_section)

        main_box.append(file_section)

        # Variables para búsqueda
        self.search_timer = None
        # Sección de acciones
        actions_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        actions_section.add_css_class("card")
        
        # Título de la sección
        actions_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions_icon = Gtk.Image.new_from_icon_name("preferences-other-symbolic")
        actions_title_box.prepend(actions_icon)
        
        actions_title_label = Gtk.Label(label=_("Acciones"))
        actions_title_label.add_css_class("title-label")
        actions_title_box.append(actions_title_label)
        
        actions_section.append(actions_title_box)
        
        # Botones de acción - Primera fila
        buttons_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box1.set_homogeneous(True)
        
        # Botón de instalar - CORREGIDO: sin label en el constructor
        self.install_button = Gtk.Button()
        self.install_button.add_css_class("action-button")
        install_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_icon = Gtk.Image.new_from_icon_name("emblem-system-symbolic")
        install_box.prepend(install_icon)
        install_label = Gtk.Label(label=_("Instalar"))
        install_box.append(install_label)
        self.install_button.set_child(install_box)
        self.install_button.connect("clicked", self.on_install_clicked)
        self.install_button.set_sensitive(False)
        buttons_box1.append(self.install_button)
        
        # Botón de corregir errores - CORREGIDO: sin label en el constructor
        self.fix_deps_button = Gtk.Button()
        self.fix_deps_button.add_css_class("secondary-button")
        fix_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fix_icon = Gtk.Image.new_from_icon_name("applications-utilities-symbolic")
        fix_box.prepend(fix_icon)
        fix_label = Gtk.Label(label=_("Corregir errores"))
        fix_box.append(fix_label)
        self.fix_deps_button.set_child(fix_box)
        self.fix_deps_button.connect("clicked", self.on_fix_deps_clicked)
        buttons_box1.append(self.fix_deps_button)
        
        actions_section.append(buttons_box1)
        
        # Segunda fila de botones
        buttons_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box2.set_homogeneous(True)
        
        # Botón de eliminar aplicaciones - CORREGIDO: sin label en el constructor
        self.apps_button = Gtk.Button()
        self.apps_button.add_css_class("secondary-button")
        apps_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apps_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic")
        apps_box.prepend(apps_icon)
        apps_label = Gtk.Label(label=_("Eliminar apps"))
        apps_box.append(apps_label)
        self.apps_button.set_child(apps_box)
        self.apps_button.connect("clicked", self.on_apps_clicked)
        buttons_box2.append(self.apps_button)
        
        # Botón de limpiar sistema - NUEVO
        self.clean_button = Gtk.Button()
        self.clean_button.add_css_class("secondary-button")
        clean_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        clean_icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic")
        clean_box.prepend(clean_icon)
        clean_label = Gtk.Label(label=_("Limpiar sistema"))
        clean_box.append(clean_label)
        self.clean_button.set_child(clean_box)
        self.clean_button.connect("clicked", self.on_clean_clicked)
        buttons_box2.append(self.clean_button)
        
        actions_section.append(buttons_box2)
        
        # Tercera fila de botones
        buttons_box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons_box3.set_homogeneous(True)
        
        # Botón de análisis antivirus - NUEVO
        self.antivirus_button = Gtk.Button()
        self.antivirus_button.add_css_class("secondary-button")
        antivirus_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        antivirus_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        antivirus_box.prepend(antivirus_icon)
        antivirus_label = Gtk.Label(label=_("Análisis antivirus"))
        antivirus_box.append(antivirus_label)
        self.antivirus_button.set_child(antivirus_box)
        self.antivirus_button.connect("clicked", self.on_antivirus_clicked)
        buttons_box3.append(self.antivirus_button)
        
        # Botón de crear PWA - NUEVO
        self.pwa_button = Gtk.Button()
        self.pwa_button.add_css_class("secondary-button")
        pwa_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pwa_icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        pwa_box.prepend(pwa_icon)
        pwa_label = Gtk.Label(label=_("Crear PWA"))
        pwa_box.append(pwa_label)
        self.pwa_button.set_child(pwa_box)
        self.pwa_button.connect("clicked", self.on_pwa_clicked)
        buttons_box3.append(self.pwa_button)
        
        actions_section.append(buttons_box3)
        main_box.append(actions_section)
        
        # Sección de progreso
        progress_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        progress_section.add_css_class("card")
        
        # Título de la sección
        progress_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        progress_icon = Gtk.Image.new_from_icon_name("emblem-synchronizing-symbolic")
        progress_title_box.prepend(progress_icon)
        
        progress_title_label = Gtk.Label(label=_("Progreso"))
        progress_title_label.add_css_class("title-label")
        progress_title_box.append(progress_title_label)
        
        progress_section.append(progress_title_box)
        
        # Barra de progreso
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        progress_section.append(self.progress_bar)
        
        # Etiqueta de estado
        self.status_label = Gtk.Label(label=_("Empieza seleccionando un archivo que contenga una app"))
        self.status_label.add_css_class("status-label")
        progress_section.append(self.status_label)
        
        main_box.append(progress_section)

        self.installed_package = None
        self.file_path = file_to_open
        
        if self.file_path:
            GLib.idle_add(self.load_initial_file)
        
        # Comprobar actualizaciones al iniciar la aplicación
        GLib.timeout_add(500, self.check_updates_on_startup)
    
    def load_initial_file(self):
        if self.file_path and os.path.exists(self.file_path):
            self.selected_file_label.set_text(_("Archivo seleccionado: {}").format(os.path.basename(self.file_path)))
            self.install_button.set_sensitive(True)
            self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
        return False
    
    def on_file_chooser_clicked(self, button):
        dialog = Gtk.FileChooserNative(
            title=_("Seleccionar paquete"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Abrir"),
            cancel_label=_("Cancelar")
        )
        
        # En GTK 4, los filtros se pueden configurar opcionalmente
        # El FileChooserNative funciona sin filtros explícitos
        
        dialog.connect("response", self._on_file_dialog_response)
        dialog.show()
    
    def _on_file_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.file_path = file.get_path()
                self.selected_file_label.set_text(_("Archivo seleccionado: {}").format(os.path.basename(self.file_path)))
                self.install_button.set_sensitive(True)
                self.status_label.set_text(_("Estoy listo para instalar: {}").format(os.path.basename(self.file_path)))
                # Limpiar la entrada de texto y ocultar resultados
                self.package_name_entry.set_text("")
                self.search_results_scrolled.set_visible(False)
        dialog.destroy()

    def create_desktop_file(self, app_name, display_name=None, icon_path=None):
        if not display_name:
            display_name = app_name
        if not icon_path:
            # Obtener la ruta del icono por defecto
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "appimage.png")

        # Determinar la extensión del icono para el destino
        icon_ext = os.path.splitext(icon_path)[1].lower()
        if not icon_ext or icon_ext not in ['.png', '.jpg', '.jpeg', '.svg', '.ico']:
            # Fallback a .png si no se detecta extensión válida
            icon_ext = '.png'
            
        target_icon_path = f"/usr/share/pixmaps/{app_name}{icon_ext}"

        # Crear el contenido del archivo .desktop
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec=/usr/bin/{app_name}
Icon={target_icon_path}
Terminal=false
Categories=Utility;
X-AppInstall=AppImage
"""
        # Escapar comillas simples para el comando echo
        escaped_content = desktop_content.replace("'", "'\\''")

        # Comando para crear el archivo .desktop y copiar el icono
        desktop_path = f"/usr/share/applications/{app_name}.desktop"
        return f"cp '{icon_path}' '{target_icon_path}' && echo '{escaped_content}' > '{desktop_path}'"

    def proceed_with_appimage_installation(self, display_name, icon_path):
        self.install_button.set_sensitive(False)
        self.fix_deps_button.set_sensitive(False)
        self.apps_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.antivirus_button.set_sensitive(False)
        self.pwa_button.set_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)

        # Nombre interno (basado en el archivo, sin espacios)
        filename = os.path.basename(self.file_path)
        app_name = os.path.splitext(filename)[0].replace(" ", "_").lower()
        
        # Crear comandos
        cmd = [
            'pkexec', 'bash', '-c',
            f'chmod +x "{self.file_path}" && ' +
            f'cp "{self.file_path}" /usr/bin/{app_name} && ' +
            self.create_desktop_file(app_name, display_name, icon_path)
        ]
        
        thread = threading.Thread(target=self.run_installation, args=(cmd,))
        thread.daemon = True
        thread.start()
    def check_updates_on_startup(self):
        thread = threading.Thread(target=self.check_updates_thread)
        thread.daemon = True
        thread.start()
        return False  # No repetir el timeout
    
    def check_updates_thread(self):
        update_info = check_for_updates()
        if update_info:
            has_update, latest_version, release_url = update_info
            if has_update:
                GLib.idle_add(self.show_update_dialog, latest_version, release_url)
    
    def show_update_dialog(self, latest_version, release_url):
        dialog = UpdateDialog(self, latest_version, release_url)
        dialog.choose(self, None, self._on_update_dialog_response, release_url)
        return False
    
    def _on_update_dialog_response(self, dialog, result, release_url):
        try:
            response = dialog.choose_finish(result)
            if response == "update":
                safe_open_url(release_url)
        except Exception as e:
            print(f"Dialog error: {e}")
    
    def on_check_updates_clicked(self, widget):
        self.status_label.set_text("Estoy comprobando las actualizaciones")
        thread = threading.Thread(target=self.manual_check_updates)
        thread.daemon = True
        thread.start()
    
    def manual_check_updates(self):
        update_info = check_for_updates()
        if update_info:
            has_update, latest_version, release_url = update_info
            if has_update:
                GLib.idle_add(self.show_update_dialog, latest_version, release_url)
            else:
                GLib.idle_add(self.show_no_updates_message)
        else:
            GLib.idle_add(self.show_update_check_error)
    
    def show_no_updates_message(self):
        dialog = Adw.AlertDialog(
            heading=_("Estoy actualizado :)"),
            body=_("Bien hecho, estoy actualizado a la última versión ({}).").format(CURRENT_VERSION)
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        self.status_label.set_text(_("Empieza seleccionando un archivo que contenga una app"))
        return False
    
    def show_update_check_error(self):
        dialog = Adw.AlertDialog(
            heading=_("He encontrado un error"),
            body=_("Vaya, no he podido comprobar las actualizaciones. ¿Estás conectado a internet?")
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(self)
        self.status_label.set_text(_("Empieza seleccionando un archivo que contenga una app"))
        return False

    def on_install_clicked(self, widget):
        # Si no hay archivo seleccionado, ver si hay algo en la entrada de texto
        if not self.file_path:
            package_name = self.package_name_entry.get_text().strip()
            if package_name:
                self.file_path = package_name
            else:
                return
            
        self.install_button.set_sensitive(False)
        self.fix_deps_button.set_sensitive(False)
        self.apps_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.antivirus_button.set_sensitive(False)
        self.pwa_button.set_sensitive(False)
        self.status_label.set_text(_("Instalando..."))
        self.progress_bar.set_fraction(0.0)

        file_extension = os.path.splitext(self.file_path)[1].lower()
        
        # Detectar si es un paquete de Homebrew
        is_brew_file = HAS_BREW and file_extension == '.rb'
        is_name_only = not file_extension

        if file_extension == '.deb' or file_extension == '.rpm':
            cmd = pkg_manager.install_local(self.file_path)
        elif is_brew_file:
            cmd = [BREW_PATH, 'install', '--formula', self.file_path]
        elif is_name_only:
            # Si tiene prefijo brew: forzamos brew
            if self.file_path.startswith('brew:'):
                pkg_name = self.file_path.replace('brew:', '', 1)
                cmd = [BREW_PATH, 'install', pkg_name]
            else:
                # Usar el gestor de paquetes del sistema
                cmd = pkg_manager.install(self.file_path)
        elif file_extension == '.appimage':
            # En lugar de instalar directamente, abrimos la ventana de configuración
            config_window = AppImageConfigWindow(self, self.file_path, self.proceed_with_appimage_installation)
            config_window.present()
            return
        elif file_extension in ('.tar.xz', '.tar.gz', '.tgz'):
            extract_dir = os.path.expanduser('~/.local')
            cmd = ['tar', '-xvf', self.file_path, '-C', extract_dir]
        else:
            self.status_label.set_text(_("Formato de paquete no soportado por App Install"))
            self.install_button.set_sensitive(True)
            self.fix_deps_button.set_sensitive(True)
            self.apps_button.set_sensitive(True)
            self.clean_button.set_sensitive(True)
            self.antivirus_button.set_sensitive(True)
            self.pwa_button.set_sensitive(True)
            return

        thread = threading.Thread(target=self.run_installation, args=(cmd,))
        thread.daemon = True
        thread.start()

    def on_fix_deps_clicked(self, widget):
        self.install_button.set_sensitive(False)
        self.fix_deps_button.set_sensitive(False)
        self.apps_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.antivirus_button.set_sensitive(False)
        self.pwa_button.set_sensitive(False)
        self.status_label.set_text(_("Corrigiendo errores"))
        self.progress_bar.set_fraction(0.0)

        cmd = pkg_manager.fix_broken()
        thread = threading.Thread(target=self.run_fix_deps, args=(cmd,))
        thread.daemon = True
        thread.start()

    def on_apps_clicked(self, widget):
        apps_window = InstalledAppsWindow(self)
        apps_window.present()

    def on_clean_clicked(self, widget):
        clean_window = SystemCleanupWindow(self)
        clean_window.present()

    def on_antivirus_clicked(self, widget):
        antivirus_window = AntivirusWindow(self)
        antivirus_window.present()

    def on_pwa_clicked(self, widget):
        pwa_window = PWAConfigWindow(self, self.proceed_with_pwa_installation)
        pwa_window.present()

    def get_pwa_command(self, url):
        """Busca el mejor navegador para ejecutar una PWA."""
        # Prioridad: Epiphany (GNOME Web), Chrome/Chromium, Brave, Edge
        if shutil.which('epiphany'):
            return f'epiphany --application-mode="{url}"'
        elif shutil.which('google-chrome'):
            return f'google-chrome --app={url}'
        elif shutil.which('google-chrome-stable'):
            return f'google-chrome-stable --app={url}'
        elif shutil.which('chromium'):
            return f'chromium --app={url}'
        elif shutil.which('chromium-browser'):
            return f'chromium-browser --app={url}'
        elif shutil.which('brave'):
            return f'brave --app={url}'
        elif shutil.which('microsoft-edge'):
            return f'microsoft-edge --app={url}'
        # Fallback al navegador por defecto (no será modo app puro)
        return f'xdg-open {url}'

    def proceed_with_pwa_installation(self, display_name, url, icon_path):
        self.install_button.set_sensitive(False)
        self.fix_deps_button.set_sensitive(False)
        self.apps_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.antivirus_button.set_sensitive(False)
        self.pwa_button.set_sensitive(False)
        self.status_label.set_text(_("Creando PWA..."))
        self.progress_bar.set_fraction(0.0)

        # Nombre interno
        app_name = display_name.lower().replace(" ", "_").replace(".", "_")
        if not app_name:
            import time
            app_name = f"pwa_{int(time.time())}"
        
        exec_cmd = self.get_pwa_command(url)
        
        # Determinar la extensión del icono para el destino
        icon_ext = os.path.splitext(icon_path)[1].lower()
        if not icon_ext or icon_ext not in ['.png', '.jpg', '.jpeg', '.svg', '.ico']:
            icon_ext = '.png'
        
        target_icon_path = f"/usr/share/pixmaps/{app_name}{icon_ext}"
        
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={display_name}
Exec={exec_cmd}
Icon={target_icon_path}
Terminal=false
Categories=Network;WebBrowser;
X-AppInstall=PWA
"""
        escaped_content = desktop_content.replace("'", "'\\''")
        desktop_path = f"/usr/share/applications/{app_name}.desktop"
        
        cmd = [
            'pkexec', 'bash', '-c',
            f"cp '{icon_path}' '{target_icon_path}' && echo '{escaped_content}' > '{desktop_path}'"
        ]
        
        thread = threading.Thread(target=self.run_installation, args=(cmd,))
        thread.daemon = True
        thread.start()

    def run_installation(self, cmd):
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            # Usar communicate() directamente para evitar bloqueos por buffer
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.installed_package = self.file_path
                
                # Mensaje especial para AppImage
                if self.file_path and self.file_path.lower().endswith('.appimage'):
                    filename = os.path.basename(self.file_path)
                    app_name = os.path.splitext(filename)[0]
                    GLib.idle_add(self.installation_complete, _("AppImage instalado como {}. Se ha creado un acceso directo.").format(app_name))
                elif not self.file_path:
                    # Probablemente una PWA
                    GLib.idle_add(self.installation_complete, _("¡Web App creada correctamente! Ya la tienes disponible en tu menú."))
                else:
                    GLib.idle_add(self.installation_complete, _("He instalado todo bien, ¡disfrútala!"))
            else:
                GLib.idle_add(self.installation_complete, _("Vaya, he encontrado un error al instalar: {}").format(stderr), True, stderr)
        except Exception as e:
            GLib.idle_add(self.installation_complete, _("Error en la instalación: {}").format(str(e)), True, "")

    def run_fix_deps(self, cmd):
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            # Usar communicate() directamente para evitar bloqueos por buffer
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                GLib.idle_add(self.fix_deps_complete, _("He arreglado las dependencias"))
            else:
                GLib.idle_add(self.fix_deps_complete, _(f"Vaya, un error al corregir dependencias: {stderr}"), True)
        except Exception as e:
            GLib.idle_add(self.fix_deps_complete, _(f"Error al corregir dependencias: {str(e)}"), True)

    def update_progress(self):
        new_value = min(1.0, self.progress_bar.get_fraction() + 0.01)
        self.progress_bar.set_fraction(new_value)
        return False

    def installation_complete(self, message, is_error=False, stderr_output=""):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        
        if is_error:
            print(f"DEBUG: Error detectado. stderr_output: {stderr_output}")  # Debug temporal
            # Verificar si el error es de dependencias faltantes
            if self.should_auto_install_deps(stderr_output):
                print("DEBUG: Dependencias faltantes detectadas, iniciando instalación automática")  # Debug temporal
                self.handle_missing_dependencies(stderr_output)
                return
                
            dialog = Adw.AlertDialog(
                heading=_(f"¡Un error en la instalación!"),
                body=message
            )
        else:
            dialog = Adw.AlertDialog(
                heading=_("He terminado la instalación"),
                body=message
            )
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        
        dialog.present(self)
        
        self.install_button.set_sensitive(True)
        self.fix_deps_button.set_sensitive(True)
        self.apps_button.set_sensitive(True)
        self.clean_button.set_sensitive(True)
        self.antivirus_button.set_sensitive(True)
        self.pwa_button.set_sensitive(True)

    def fix_deps_complete(self, message, is_error=False):
        self.progress_bar.set_fraction(1.0)
        self.status_label.set_text(message)
        
        if is_error:
            dialog = Adw.AlertDialog(
                heading=_("¡Un error al corregir las dependencias!"),
                body=message
            )
        else:
            dialog = Adw.AlertDialog(
                heading=_("He corregido las dependencias"),
                body=message
            )
        
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        
        dialog.present(self)
        
        self.install_button.set_sensitive(True)
        self.fix_deps_button.set_sensitive(True)
        self.apps_button.set_sensitive(True)
        self.clean_button.set_sensitive(True)
        self.antivirus_button.set_sensitive(True)
        self.pwa_button.set_sensitive(True)

    def should_auto_install_deps(self, stderr_output):
        """Determina si el error se debe a dependencias faltantes."""
        if not stderr_output:
            print("DEBUG: No hay stderr_output")  # Debug temporal
            return False
            
        # Patrones comunes que indican dependencias faltantes (inglés y español)
        dependency_patterns = [
            # Patrones en inglés
            "depends on",
            "dependency is not satisfiable", 
            "unmet dependencies",
            "depends:",
            "pre-depends:",
            "Dependency is not satisfiable:",
            "broken dependencies",
            "conflicting packages",
            "package has unmet dependencies",
            "dependency problems",
            "trying to overwrite",
            "dpkg: dependency problems prevent",
            "Error: Package:",
            "requires:",
            "but is not installable",
            "Broken packages",
            "configure: error",
            # Patrones en español
            "depende de",
            "problemas de dependencias",
            "dependencias - se deja sin configurar",
            "no está instalado",
            "sin embargo:",
            "dpkg: problemas de dependencias impiden",
            "error al procesar el paquete",
            "dependencias no satisfechas",
            "paquete no está instalado",
            "Error: El paquete:",
            "necesita:",
            "requiere:"
        ]
        
        stderr_lower = stderr_output.lower()
        found_pattern = None
        for pattern in dependency_patterns:
            if pattern.lower() in stderr_lower:
                found_pattern = pattern
                break
        
        print(f"DEBUG: Buscando patrones de dependencias. Encontrado: {found_pattern}")  # Debug temporal
        return found_pattern is not None

    def extract_missing_packages(self, stderr_output):
        """Extrae los nombres de paquetes faltantes del error con mejor precisión."""
        import re
        
        missing_packages = set()
        
        # Patrones para extraer nombres de paquetes (inglés y español)
        patterns = [
            # Patrones en inglés
            r'(\w+(?:[-_]\w+)*)\s*\([^)]*\)\s*but',
            r'depends\s+on\s+(\w+(?:[-_]\w+)*)',
            r'(\w+(?:[-_]\w+)*)\s*:\s*Depends:',
            r'Depends:\s*(\w+(?:[-_]\w+)*)',
            r'package\s+(\w+(?:[-_]\w+)*)\s+is\s+not\s+installed',
            r'The following packages have unmet dependencies:',
            # Patrones en español
            r'depende\s+de\s+([a-zA-Z0-9][a-zA-Z0-9\-\.]*)',
            r'El\s+paquete\s+[`\'""]([a-zA-Z0-9][a-zA-Z0-9\-\.]*)[`\'""]\s+no\s+está\s+instalado',
            r'([a-zA-Z0-9][a-zA-Z0-9\-\.]*)\s+\([^)]*\);\s+sin\s+embargo:',
            r'([a-zA-Z0-9][a-zA-Z0-9\-\.]*)\s+depende\s+de',
            r'Problemas de dependencias - se deja sin configurar'
        ]
        
        # Bloques de error comunes de apt/dpkg
        if "unmet dependencies" in stderr_output.lower() or "problemas de dependencias" in stderr_output.lower():
            # Intentar extraer paquetes después de "Depends:" o "depende de"
            lines = stderr_output.split('\n')
            for line in lines:
                if "Depends:" in line or "depende de" in line:
                    # Extraer el nombre del paquete (suele ser la primera palabra después del prefijo)
                    match = re.search(r'(?:Depends:|depende de)\s+([a-zA-Z0-9][a-zA-Z0-9\-\.]*)', line)
                    if match:
                        missing_packages.add(match.group(1))
        
        for pattern in patterns:
            matches = re.findall(pattern, stderr_output, re.IGNORECASE)
            for m in matches:
                if isinstance(m, str):
                    missing_packages.add(m)
                elif isinstance(m, tuple) and m[0]:
                    missing_packages.add(m[0])
        
        # Filtrar paquetes comunes que no necesitan instalación manual y palabras de control
        filter_out = {
            'but', 'is', 'not', 'installed', 'depends', 'on', 'package', 'de', 'el', 'paquete', 
            'sin', 'embargo', 'the', 'following', 'packages', 'have', 'unmet', 'dependencies',
            'problemas', 'configurar', 'deja'
        }
        missing_packages = {pkg for pkg in missing_packages if pkg.lower() not in filter_out and len(pkg) > 2}
        
        return list(missing_packages)

    def handle_missing_dependencies(self, stderr_output):
        """Maneja la instalación automática de dependencias faltantes."""
        print(f"DEBUG: Manejando dependencias faltantes...")  # Debug temporal
        missing_packages = self.extract_missing_packages(stderr_output)
        print(f"DEBUG: Paquetes faltantes detectados: {missing_packages}")  # Debug temporal
        
        if not missing_packages:
            print("DEBUG: No se detectaron paquetes específicos, usando auto_fix_dependencies")  # Debug temporal
            # Si no podemos detectar paquetes específicos, intentar la corrección general
            self.auto_fix_dependencies()
            return
        
        # Mostrar diálogo de confirmación
        packages_text = ", ".join(missing_packages)
        print(f"DEBUG: Mostrando diálogo para instalar: {packages_text}")  # Debug temporal
        dialog = Adw.AlertDialog(
            heading="Dependencias faltantes detectadas",
            body=f"He detectado que faltan estas dependencias:\n{packages_text}\n\n¿Quieres que las instale automáticamente?"
        )
        dialog.add_response("no", "No")
        dialog.add_response("yes", "Sí, instalar")
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("yes")
        dialog.set_close_response("no")
        
        dialog.choose(self, None, self._on_auto_install_response, missing_packages)

    def _on_auto_install_response(self, dialog, result, missing_packages):
        """Respuesta del diálogo de instalación automática."""
        try:
            response = dialog.choose_finish(result)
            if response == "yes":
                self.install_missing_packages(missing_packages)
        except Exception as e:
            print(f"Dialog error: {e}")

    def install_missing_packages(self, packages):
        """Instala los paquetes faltantes."""
        self.status_label.set_text("Instalando dependencias faltantes...")
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        
        # Construir comando para instalar paquetes
        cmd = pkg_manager.install_multiple(packages)
        
        thread = threading.Thread(target=self.run_auto_dependency_install, args=(cmd, packages))
        thread.daemon = True
        thread.start()

    def run_auto_dependency_install(self, cmd, packages):
        """Ejecuta la instalación de dependencias en un hilo separado."""
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_progress)
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                GLib.idle_add(self.auto_install_complete, packages, True)
            else:
                GLib.idle_add(self.auto_install_complete, packages, False, stderr)
        except Exception as e:
            GLib.idle_add(self.auto_install_complete, packages, False, str(e))

    def auto_install_complete(self, packages, success, error_msg=""):
        """Maneja el resultado de la instalación automática."""
        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        
        if success:
            self.status_label.set_text("Dependencias instaladas. Reintentando instalación...")
            # Reintentar la instalación del paquete original
            self.retry_installation()
        else:
            self.status_label.set_text("Error al instalar dependencias")
            dialog = Adw.AlertDialog(
                heading="Error al instalar dependencias",
                body=f"No pude instalar las dependencias automáticamente.\nError: {error_msg}\n\nPuedes intentar corregir manualmente usando el botón 'Corregir errores'."
            )
            dialog.add_response("ok", "OK")
            dialog.set_default_response("ok")
            dialog.present(self)
            
            # Re-habilitar botones
            self.install_button.set_sensitive(True)
            self.fix_deps_button.set_sensitive(True)
            self.apps_button.set_sensitive(True)
            self.clean_button.set_sensitive(True)
            self.antivirus_button.set_sensitive(True)
            self.pwa_button.set_sensitive(True)

    def auto_fix_dependencies(self):
        """Ejecuta apt-get install -f automáticamente."""
        print("DEBUG: Ejecutando auto_fix_dependencies")  # Debug temporal
        
        # Mostrar diálogo de confirmación para la corrección automática
        dialog = Adw.AlertDialog(
            heading="Error de dependencias detectado",
            body="He detectado un problema con las dependencias del paquete.\n\n¿Quieres que intente corregir las dependencias automáticamente?"
        )
        dialog.add_response("no", "No")
        dialog.add_response("yes", "Sí, corregir")
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("yes")
        dialog.set_close_response("no")
        
        dialog.choose(self, None, self._on_auto_fix_response, None)

    def _on_auto_fix_response(self, dialog, result, data):
        """Respuesta del diálogo de corrección automática."""
        try:
            response = dialog.choose_finish(result)
            if response == "yes":
                print("DEBUG: Usuario confirmó corrección automática")  # Debug temporal
                self.status_label.set_text("Corrigiendo dependencias automáticamente...")
                self.progress_bar.set_fraction(0.0)
                self.progress_bar.set_visible(True)
                
                cmd = pkg_manager.fix_broken()
                thread = threading.Thread(target=self.run_auto_fix, args=(cmd,))
                thread.daemon = True
                thread.start()
            else:
                print("DEBUG: Usuario canceló corrección automática")  # Debug temporal
                # Re-habilitar botones si el usuario cancela
                self.install_button.set_sensitive(True)
                self.fix_deps_button.set_sensitive(True)
                self.apps_button.set_sensitive(True)
                self.clean_button.set_sensitive(True)
                self.antivirus_button.set_sensitive(True)
                self.pwa_button.set_sensitive(True)
        except Exception as e:
            print(f"Dialog error: {e}")

    def run_auto_fix(self, cmd):
        """Ejecuta la corrección automática de dependencias."""
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    GLib.idle_add(self.update_progress)
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                GLib.idle_add(self.auto_fix_complete, True)
            else:
                GLib.idle_add(self.auto_fix_complete, False, stderr)
        except Exception as e:
            GLib.idle_add(self.auto_fix_complete, False, str(e))

    def auto_fix_complete(self, success, error_msg=""):
        """Maneja el resultado de la corrección automática."""
        self.progress_bar.set_visible(False)
        self.progress_bar.set_fraction(0.0)
        
        if success:
            self.status_label.set_text("Dependencias corregidas. Reintentando instalación...")
            # Reintentar la instalación del paquete original
            self.retry_installation()
        else:
            self.status_label.set_text("Error al corregir dependencias automáticamente")
            dialog = Adw.AlertDialog(
                heading="Error al corregir dependencias",
                body=f"No pude corregir las dependencias automáticamente.\nError: {error_msg}"
            )
            dialog.add_response("ok", "OK")
            dialog.set_default_response("ok")
            dialog.present(self)
            
            # Re-habilitar botones
            self.install_button.set_sensitive(True)
            self.fix_deps_button.set_sensitive(True)
            self.apps_button.set_sensitive(True)
            self.clean_button.set_sensitive(True)
            self.antivirus_button.set_sensitive(True)
            self.pwa_button.set_sensitive(True)

    def retry_installation(self):
        """Reintenta la instalación del paquete original después de corregir dependencias."""
        if not self.file_path:
            return
            
        self.status_label.set_text("Reintentando instalación...")
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_visible(True)
        
        # Reconstruir el comando de instalación
        file_extension = os.path.splitext(self.file_path)[1].lower()
        
        if file_extension == '.deb' or file_extension == '.rpm':
            cmd = pkg_manager.install_local(self.file_path)
        elif file_extension == '.appimage':
            # Para AppImage usamos la nueva lógica (aunque reintentar AppImage es raro)
            config_window = AppImageConfigWindow(self, self.file_path, self.proceed_with_appimage_installation)
            config_window.present()
            return
        elif file_extension in ('.tar.xz', '.tar.gz', '.tgz'):
            extract_dir = os.path.expanduser('~/.local')
            cmd = ['tar', '-xvf', self.file_path, '-C', extract_dir]
        else:
            self.status_label.set_text("Formato de paquete no soportado")
            return
        
        thread = threading.Thread(target=self.run_installation, args=(cmd,))
        thread.daemon = True
        thread.start()

    def on_report_issue(self, widget):
        safe_open_url("https://github.com/Inled-Group/appinstall/issues")
    
    def open_inled_es(self, widget):
        safe_open_url("https://inled.es")
    
    def on_package_name_changed(self, entry):
        text = entry.get_text().strip()
        
        # Si hay texto, anulamos la selección de archivo previo para evitar confusiones
        if text:
            if self.file_path:
                self.file_path = None
                self.selected_file_label.set_text(_("Aún no has seleccionado ningún archivo"))
            self.install_button.set_sensitive(True)
        elif not self.file_path:
            self.install_button.set_sensitive(False)

        # Gestionar la búsqueda con un pequeño retraso (debounce)
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = None

        if len(text) >= 3:
            self.search_timer = GLib.timeout_add(500, self.perform_package_search, text)
        else:
            self.search_results_scrolled.set_visible(False)

    def perform_package_search(self, query):
        self.search_timer = None
        # Mostrar y activar spinner
        self.search_spinner.set_visible(True)
        self.search_spinner.start()
        # Ocultar resultados anteriores mientras busca
        self.search_results_scrolled.set_visible(False)
        
        thread = threading.Thread(target=self.search_thread, args=(query,))
        thread.daemon = True
        thread.start()
        return False

    def search_thread(self, query):
        results = []

        # Buscar usando el gestor de paquetes del sistema
        try:
            results.extend(pkg_manager.search(query)[:15]) # Limitar resultados
        except:
            pass

        # Buscar en Homebrew

        if HAS_BREW:
            print(f"DEBUG: Buscando '{query}' en Homebrew usando {BREW_PATH}")
            try:
                brew_output = subprocess.check_output([BREW_PATH, 'search', query], 
                                                    timeout=10, stderr=subprocess.STDOUT).decode('utf-8')
                found_count = 0
                for line in brew_output.split('\n')[:15]:
                    if line.strip() and not line.startswith('=='):
                        results.append({'name': line.strip(), 'desc': _("Fórmula de Homebrew"), 'source': 'brew'})
                        found_count += 1
                print(f"DEBUG: Encontrados {found_count} resultados en Homebrew")
            except Exception as e:
                print(f"DEBUG: Error en búsqueda de Homebrew: {e}")
        else:
            print("DEBUG: Salto búsqueda de Homebrew (no detectado)")
        
        GLib.idle_add(self.show_search_results, results)

    def show_search_results(self, results):
        # Detener y ocultar spinner
        self.search_spinner.stop()
        self.search_spinner.set_visible(False)
        
        # Limpiar lista anterior
        child = self.search_results_list.get_first_child()
        while child:
            self.search_results_list.remove(child)
            child = self.search_results_list.get_first_child()

        if not results:
            self.search_results_scrolled.set_visible(False)
            return

        for res in results:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(6)
            box.set_margin_bottom(6)
            box.set_margin_start(12)
            box.set_margin_end(12)
            
            icon_name = "package-x-generic-symbolic" if res['source'] == 'apt' else "system-software-install-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_opacity(0.7)
            box.append(icon)
            
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            name_label = Gtk.Label(label=res['name'], xalign=0)
            name_label.add_css_class("title-label") 
            vbox.append(name_label)
            
            desc_label = Gtk.Label(label=res['desc'], xalign=0)
            desc_label.set_ellipsize(3) # Pango.EllipsizeMode.END
            desc_label.add_css_class("subtitle-label")
            desc_label.set_opacity(0.8)
            vbox.append(desc_label)
            
            box.append(vbox)
            row.set_child(box)
            # Guardar datos en el row para recuperarlos al activar
            row.pkg_name = res['name']
            row.source = res['source']
            
            self.search_results_list.append(row)
        
        self.search_results_scrolled.set_visible(True)

    def on_search_result_activated(self, listbox, row):
        pkg_name = row.pkg_name
        if row.source == 'brew':
            pkg_name = f"brew:{pkg_name}"
            
        self.package_name_entry.set_text(pkg_name)
        self.search_results_scrolled.set_visible(False)
        self.install_button.set_sensitive(True)

    def on_about_clicked(self, widget):
        about_dialog = Adw.AboutWindow(
            transient_for=self,
            modal=True,
            application_name="App Install",
            application_icon="es.inled.AppInstall",
            version=CURRENT_VERSION,
            comments=_("Instalador de paquetes gráfico para Linux."),
            copyright="© 2026 Inled Group",
            license_type=Gtk.License.CUSTOM,
            license="MIT-INLED",
            website="https://license.inled.es",
            developers=["Inled Group"]
        )
        
        # Intentar cargar icono local si no se encuentra en el tema
        local_icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), "es.inled.AppInstall.png")
        if os.path.exists(local_icon):
            try:
                texture = Gdk.Texture.new_from_filename(local_icon)
                about_dialog.set_application_icon_paintable(texture)
            except Exception as e:
                print(f"No se pudo cargar el icono desde archivo: {e}")
                
        about_dialog.present()
def check_dependencies():
    """Verifica que todas las dependencias necesarias estén instaladas."""
    missing_deps = []
    
    # Verificar Python
    try:
        import sys
        python_version = sys.version_info
        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 6):
            missing_deps.append(f"Python 3.6+ (versión actual: {python_version.major}.{python_version.minor})")
    except:
        missing_deps.append("Python 3.6+")
    
    # Verificar dependencias de GTK
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
    except ImportError:
        missing_deps.append("PyGObject (python3-gi)")
    except ValueError:
        missing_deps.append("GTK 3.0 (libgtk-3-0)")
    
    # Verificar otras dependencias de Python
    dependencies = [
        ('requests', 'requests'),
        ('packaging', 'packaging'),
    ]
    
    for module_name, package_name in dependencies:
        try:
            __import__(module_name)
        except ImportError:
            missing_deps.append(f"{package_name}")
    
    return missing_deps

def show_dependencies_dialog(parent_window, missing_deps):
    """Muestra un diálogo con las dependencias faltantes."""
    if not missing_deps:
        return True
    
    from gi.repository import Gtk
    
    deps_text = "\n".join([f"• {dep}" for dep in missing_deps])
    install_cmd = "sudo apt install python3 python3-gi python3-requests python3-packaging libgtk-3-0"
    
    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text="Faltan dependencias requeridas"
    )
    
    if parent_window:
        dialog.present(parent_window)
    else:
        dialog.present(None)
    
    return False  # Indicar que faltan dependencias

class AppInstallApp(Adw.Application):
    def __init__(self):
        # El ID debe coincidir con el nombre del archivo .desktop para una integración perfecta en GNOME
        super().__init__(application_id="es.inled.AppInstall", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.connect("activate", self.on_activate)
        self.connect("command-line", self.on_command_line)
        self.file_to_open = None
        
        # Establecer el nombre del programa y la aplicación
        GLib.set_prgname("es.inled.AppInstall")
        GLib.set_application_name("App Install")
    
    def on_command_line(self, app, command_line):
        args = command_line.get_arguments()
        if len(args) > 1:
            file_path = args[1]
            if not os.path.isabs(file_path):
                cwd = command_line.get_cwd()
                file_path = os.path.join(cwd, file_path)
            self.file_to_open = file_path
        
        app.activate()
        return 0

    def on_activate(self, app):
        # Buscar si ya hay una ventana abierta
        windows = app.get_windows()
        if windows:
            windows[0].present()
            if self.file_to_open:
                windows[0].file_path = self.file_to_open
                windows[0].load_initial_file()
            return

        # Configurar el tema de iconos para incluir el directorio local (para ejecución sin instalar)
        setup_icon_theme()

        missing_deps = check_dependencies()
        # Cargar el CSS para el estilo GNOME moderno
        load_css()
        
        win = PackageInstaller(app, file_to_open=self.file_to_open)
        win.present()

def Component():
    # Inicializar el tema de iconos antes de crear la app
    setup_icon_theme()
    app = AppInstallApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    try:
        Component()
    except Exception as e:
        import traceback
        error_log = os.path.expanduser("~/.cache/appinstall_error.log")
        with open(error_log, "w") as f:
            f.write(f"Error starting AppInstall: {str(e)}\n")
            traceback.print_exc(file=f)
        # Intentar mostrar dialogo de error con zenity si es posible, o print
        print(f"Critical error: {e}", file=sys.stderr)
        sys.exit(1)
 