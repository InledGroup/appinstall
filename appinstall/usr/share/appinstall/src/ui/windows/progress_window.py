from gi.repository import Gtk, Adw
from src.infrastructure.services.localization import _

# English: Window that shows loading progress, allows skipping details analysis,
# shows a toggle for the operation log, and can be closed while running.
# Español: Ventana que muestra el progreso de carga, permite omitir el análisis
# de detalles, incluye un botón para mostrar/ocultar el registro y se puede cerrar.
class ProgressWindow(Adw.Window):
    def __init__(self, parent, message, skip_callback=None):
        super().__init__()
        # Resolve root window if a widget is passed instead of a window
        if not isinstance(parent, Gtk.Window):
            parent = parent.get_root()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(True)
        self.set_default_size(480, 460)

        self.log_visible = False

        toolbar_view = Adw.ToolbarView()

        # English: Header bar with close button so the operation can be dismissed
        # Español: Barra de cabecera con botón de cierre para poder descartar la operación
        header_bar = Adw.HeaderBar()
        header_bar.set_show_end_title_buttons(True)
        header_bar.add_css_class("header-bar")
        header_bar.set_title_widget(Adw.WindowTitle(title=_("Operación en curso")))
        toolbar_view.add_top_bar(header_bar)

        # English: Main vertical box container
        # Español: Contenedor de caja vertical principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_valign(Gtk.Align.FILL)
        main_box.set_halign(Gtk.Align.FILL)
        main_box.set_margin_top(16)
        main_box.set_margin_bottom(16)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)

        # English: Status content (spinner + message) centered
        # Español: Contenido de estado (spinner + mensaje) centrado
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        status_box.set_valign(Gtk.Align.CENTER)
        status_box.set_halign(Gtk.Align.CENTER)
        status_box.set_vexpand(True)

        # English: Large activity spinner
        # Español: Indicador de actividad (spinner) grande
        spinner = Gtk.Spinner()
        spinner.set_size_request(80, 80)
        spinner.start()
        status_box.append(spinner)

        # English: Status label
        # Español: Etiqueta de estado
        self.label = Gtk.Label(label=message)
        self.label.add_css_class("title-label")
        self.label.set_wrap(True)
        self.label.set_max_width_chars(30)
        self.label.set_justify(Gtk.Justification.CENTER)
        status_box.append(self.label)

        main_box.append(status_box)

        # English: Optional action button to skip details and install directly
        # Español: Botón de acción opcional para saltar detalles e instalar directamente
        if skip_callback:
            skip_btn = Gtk.Button(label=_("Instalar directamente"))
            skip_btn.add_css_class("suggested-action")
            skip_btn.set_margin_top(12)
            skip_btn.set_halign(Gtk.Align.CENTER)
            skip_btn.connect("clicked", lambda btn: self._on_skip_clicked(skip_callback))
            main_box.append(skip_btn)

        # English: Toggle for showing/hiding the operation log
        # Español: Botón para mostrar/ocultar el registro de la operación
        self.log_toggle = Gtk.ToggleButton()
        self.log_toggle_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.log_toggle_icon = Gtk.Image.new_from_icon_name("view-list-symbolic")
        self.log_toggle_box.append(self.log_toggle_icon)
        self.log_toggle_label = Gtk.Label(label=_("Mostrar registro"))
        self.log_toggle_box.append(self.log_toggle_label)
        self.log_toggle.set_child(self.log_toggle_box)
        self.log_toggle.set_halign(Gtk.Align.CENTER)
        self.log_toggle.add_css_class("flat")
        self.log_toggle.connect("toggled", self._on_log_toggled)
        main_box.append(self.log_toggle)

        # English: Log area (hidden by default)
        # Español: Área de registro (oculta por defecto)
        self.log_scrolled = Gtk.ScrolledWindow()
        self.log_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_scrolled.set_min_content_height(160)
        self.log_scrolled.set_max_content_height(240)
        self.log_scrolled.set_vexpand(True)
        self.log_scrolled.set_visible(False)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_view.add_css_class("log-view")
        self.log_buffer = self.log_view.get_buffer()
        self.log_scrolled.set_child(self.log_view)

        main_box.append(self.log_scrolled)

        toolbar_view.set_content(main_box)
        self.set_content(toolbar_view)

    def _on_log_toggled(self, toggle):
        # English: Show/hide the log area and update the toggle label
        # Español: Mostrar/ocultar el área de registro y actualizar la etiqueta
        active = toggle.get_active()
        self.log_visible = active
        self.log_scrolled.set_visible(active)
        if active:
            self.log_toggle_label.set_text(_("Ocultar registro"))
        else:
            self.log_toggle_label.set_text(_("Mostrar registro"))

    def append_log(self, line):
        # English: Append a line to the log and scroll to the end
        # Español: Añadir una línea al registro y desplazarse al final
        try:
            end_iter = self.log_buffer.get_end_iter()
            self.log_buffer.insert(end_iter, line + "\n")
            mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
            self.log_scrolled.scroll_to_mark(mark, 0.0, False, 0.0, 0.0)
        except Exception:
            pass

    def auto_show_log(self):
        # English: Force the log to be visible (used on errors)
        # Español: Forzar que el registro sea visible (usado ante errores)
        if not self.log_toggle.get_active():
            self.log_toggle.set_active(True)

    def _on_skip_clicked(self, skip_callback):
        # English: Close progress window and trigger skip callback
        # Español: Cerrar la ventana de progreso y disparar el callback de salto
        self.close()
        skip_callback()

    def update_message(self, message):
        self.label.set_text(message)
