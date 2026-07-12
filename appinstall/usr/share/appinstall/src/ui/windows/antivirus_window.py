import os
import threading
from gi.repository import Gtk, GLib, Adw
from src.infrastructure.services.localization import _
from src.utils.system import get_safe_window_size

from .progress_window import ProgressWindow

class AntivirusWidget(Gtk.Box):
    def __init__(self, parent, antivirus_service):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.antivirus_service = antivirus_service
        self.add_css_class("main-window")

        # Header bar al estilo GNOME
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(False)
        header_bar.set_show_start_title_buttons(False)
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Análisis de virus")))
        header_bar.add_css_class("header-bar")

        # Contenido principal en un ToolbarView
        toolbar_view = Adw.ToolbarView()
        toolbar_view.set_hexpand(True)
        toolbar_view.set_vexpand(True)
        toolbar_view.add_top_bar(header_bar)
        self.append(toolbar_view)

        # Crear scrolled window para el contenido principal
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

        scan_type_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scan_type_label = Gtk.Label(label=_("Tipo de análisis:"), xalign=0)
        scan_type_label.add_css_class("title-label")
        scan_type_box.append(scan_type_label)

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
        self.custom_scan_radio.connect("toggled", self.on_custom_toggled)
        main_box.append(config_section)

        # Sección de opciones avanzadas
        advanced_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        advanced_section.add_css_class("card")
        adv_title = Gtk.Label(label=_("Opciones avanzadas"))
        adv_title.add_css_class("title-label")
        advanced_section.append(adv_title)

        self.update_defs_check = Gtk.CheckButton()
        self.update_defs_check.set_active(True)
        update_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        update_box.prepend(self.update_defs_check)
        update_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        update_label = Gtk.Label(label=_("Actualizar definiciones antes del análisis"), xalign=0)
        update_label.add_css_class("title-label")
        update_info.append(update_label)
        update_desc = Gtk.Label(label=_("Descargar las últimas actualizaciones de definiciones de virus"), xalign=0)
        update_desc.add_css_class("subtitle-label")
        update_info.append(update_desc)
        update_box.append(update_info)
        advanced_section.append(update_box)

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

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("progress-bar")
        self.progress_bar.set_visible(False)
        main_box.append(self.progress_bar)

        self.status_label = Gtk.Label(label=_("Listo para iniciar análisis"))
        self.status_label.add_css_class("status-label")
        main_box.append(self.status_label)

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

        self.is_clam_installed = False
        GLib.timeout_add(500, lambda: self.antivirus_service.check_clamav_status(self.on_clam_status_complete))

    def on_clam_status_complete(self, installed, version):
        if installed:
            self.is_clam_installed = True
            self.clam_status_label.set_text(f"✅ ClamAV instalado: {version}")
            self.install_clam_button.set_visible(False)
            self.scan_button.set_sensitive(True)
            self.update_button.set_sensitive(True)
        else:
            self.is_clam_installed = False
            self.clam_status_label.set_text("❌ ClamAV no está instalado")
            self.install_clam_button.set_visible(True)
            self.scan_button.set_sensitive(False)
            self.update_button.set_sensitive(False)
        return False

    def on_custom_toggled(self, button):
        self.custom_dir_box.set_sensitive(self.custom_scan_radio.get_active())

    def on_browse_clicked(self, button):
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
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.custom_dir_entry.set_text(file.get_path())
        dialog.destroy()

    def on_install_clam_clicked(self, button):
        dialog = Adw.AlertDialog(
            heading=_("Instalar ClamAV"),
            body=_("¿Quieres instalar ClamAV y sus definiciones de virus?\n\nEsto puede tardar varios minutos.")
        )
        dialog.add_response("cancel", _("Cancelar"))
        dialog.add_response("install", _("Instalar"))
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")
        dialog.choose(self, None, self._on_install_clam_response, None)

    def _on_install_clam_response(self, dialog, result, data):
        try:
            response = dialog.choose_finish(result)
            if response == "install":
                self.install_clam_button.set_sensitive(False)
                self.progress_bar.set_visible(True)
                self.progress_bar.set_fraction(0.0)
                self.status_label.set_text(_("Instalando ClamAV..."))
                
                self.progress_dialog = ProgressWindow(self, _("Instalando ClamAV..."))
                self.progress_dialog.present()
                
                self.antivirus_service.install_clamav(self.update_install_progress, self.update_status_label, self.install_clam_complete)
        except Exception as e:
            print(f"Dialog error: {e}")

    def update_install_progress(self):
        self.progress_bar.set_fraction(min(1.0, self.progress_bar.get_fraction() + 0.02))
        return False

    def update_status_label(self, message):
        self.status_label.set_text(message)
        return False

    def install_clam_complete(self, success, error_msg):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.progress_bar.set_visible(False)
        self.install_clam_button.set_sensitive(True)
        if success:
            self.status_label.set_text(_("ClamAV instalado correctamente"))
            GLib.timeout_add(1000, lambda: self.antivirus_service.check_clamav_status(self.on_clam_status_complete))
        else:
            self.status_label.set_text(_(f"Error instalando ClamAV: {error_msg}"))
        return False

    def on_update_clicked(self, button):
        self.update_button.set_sensitive(False)
        self.scan_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Actualizando definiciones de virus..."))
        
        self.progress_dialog = ProgressWindow(self, _("Actualizando definiciones..."))
        self.progress_dialog.present()
        
        self.antivirus_service.update_definitions(self.update_defs_progress, self.update_definitions_complete)

    def update_defs_progress(self):
        self.progress_bar.set_fraction(min(1.0, self.progress_bar.get_fraction() + 0.05))
        return False

    def update_definitions_complete(self, success, error_msg):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.progress_bar.set_visible(False)
        self.update_button.set_sensitive(True)
        self.scan_button.set_sensitive(True)
        if success:
            self.status_label.set_text(_("Definiciones actualizadas correctamente"))
        else:
            self.status_label.set_text(_(f"Error actualizando definiciones: {error_msg}"))
        return False

    def on_scan_clicked(self, button):
        if self.update_defs_check.get_active():
            self.on_update_clicked(button)
            GLib.timeout_add(2000, self.check_and_start_scan)
        else:
            self.start_scan()

    def check_and_start_scan(self):
        if not self.progress_bar.get_visible():
            self.start_scan()
            return False
        return True

    def start_scan(self):
        self.scan_button.set_sensitive(False)
        self.update_button.set_sensitive(False)
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.status_label.set_text(_("Iniciando análisis antivirus..."))
        self.results_text.get_buffer().set_text("")
        
        self.progress_dialog = ProgressWindow(self, _("Analizando virus..."))
        self.progress_dialog.present()
        
        if self.quick_scan_radio.get_active():
            scan_paths = [os.path.expanduser("~"), "/tmp", "/var/tmp"]
        elif self.full_scan_radio.get_active():
            scan_paths = ["/"]
        else:
            scan_paths = [self.custom_dir_entry.get_text()]
            
        self.antivirus_service.run_scan(scan_paths, self.deep_scan_check.get_active(), 
                                      self.update_scan_progress, self.append_result, self.scan_complete)

    def update_scan_progress(self):
        self.progress_bar.set_fraction(min(0.95, self.progress_bar.get_fraction() + 0.01))
        return False

    def append_result(self, text):
        buffer = self.results_text.get_buffer()
        buffer.insert(buffer.get_end_iter(), text)
        self.results_text.scroll_to_mark(buffer.get_insert(), 0.0, False, 0.0, 0.0)
        return False

    def scan_complete(self, success, infected_count, scanned_count, stderr):
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.progress_bar.set_fraction(1.0)
        self.scan_button.set_sensitive(True)
        self.update_button.set_sensitive(True)
        
        if success:
            if infected_count == 0:
                status = f"✅ Análisis completado. He revisado {scanned_count} archivos y no he encontrado amenazas."
            else:
                status = f"⚠️ He encontrado {infected_count} amenazas en {scanned_count} archivos analizados."
                self.show_threat_dialog(infected_count)
            self.append_result(f"\n{status}\n")
            self.status_label.set_text(status)
        else:
            self.status_label.set_text(_(f"Error en el análisis: {stderr}"))
            
        GLib.timeout_add(2000, lambda: self.progress_bar.set_visible(False))
        return False

    def show_threat_dialog(self, threat_count):
        dialog = Adw.AlertDialog(
            heading=_("⚠️ ¡Cuidado!"),
            body=_(f"He detectado {threat_count} amenazas en tu sistema.\n\n¿Qué quieres hacer?")
        )
        dialog.add_response("ignore", _("Ignorar"))
        dialog.add_response("quarantine", _("Poner en cuarentena"))
        dialog.add_response("delete", _("Eliminar amenazas"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("quarantine")
        dialog.choose(self.get_root(), None, None, None)
