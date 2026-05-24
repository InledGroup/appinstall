import threading
from gi.repository import Gtk, GLib, Adw
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size

class SystemCleanupWindow(Adw.Window):
    def __init__(self, parent, cleanup_service):
        super().__init__()
        self.cleanup_service = cleanup_service
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

        # Contenido desplazable
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

        self.directory_checks = {}
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
            check.set_active(True)
            self.directory_checks[directory] = check
            check_box.prepend(check)
            
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

        self.total_size = 0

    def on_analyze_clicked(self, button):
        self.analyze_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Analizando archivos..."))
        
        selected_dirs = [d for d, check in self.directory_checks.items() if check.get_active()]
        self.cleanup_service.run_analysis(selected_dirs, self.orphan_check.get_active(), self.apt_check.get_active(),
                                        self.update_progress, self.analysis_complete)

    def update_progress(self, fraction):
        self.progress_bar.set_fraction(fraction)
        return False

    def analysis_complete(self, success, total_size, error_msg):
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        
        if success:
            self.total_size = total_size
            self.clean_button.set_sensitive(True)
            size_str = self.format_size(total_size)
            self.status_label.set_text(_("Análisis completo. Se pueden liberar: {}").format(size_str))
        else:
            self.status_label.set_text(_(f"Error en el análisis: {error_msg}"))
        return False

    def format_size(self, size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def on_clean_clicked(self, button):
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
        try:
            response = dialog.choose_finish(result)
            if response == "clean":
                self.start_cleanup()
        except Exception as e:
            print(f"Dialog error: {e}")

    def start_cleanup(self):
        self.analyze_button.set_sensitive(False)
        self.clean_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Limpiando archivos..."))
        
        selected_dirs = [d for d, check in self.directory_checks.items() if check.get_active()]
        self.cleanup_service.run_cleanup(selected_dirs, self.orphan_check.get_active(), self.apt_check.get_active(),
                                       self.update_progress, self.cleanup_complete)

    def cleanup_complete(self, success, cleaned_size, error_msg):
        self.progress_bar.set_visible(False)
        self.analyze_button.set_sensitive(True)
        
        if success:
            self.clean_button.set_sensitive(False)
            size_str = self.format_size(cleaned_size)
            self.status_label.set_text(_("Limpieza completada. Espacio liberado: {}").format(size_str))
            
            dialog = Adw.AlertDialog(
                heading=_("¡Ya he terminado!"),
                body=_("He dejado impoluto tu Linux.\n\nHe liberado {} que estaban ocupando espacio sin necesidad.").format(size_str)
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            dialog.present(self)
        else:
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
