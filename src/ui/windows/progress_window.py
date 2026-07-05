from gi.repository import Gtk, Adw
from src.infrastructure.services.localization import _

# English: Window that shows loading progress and allows skipping details analysis
# Español: Ventana que muestra el progreso de carga y permite omitir el análisis de detalles
class ProgressWindow(Adw.Window):
    def __init__(self, parent, message, skip_callback=None):
        super().__init__()
        # Resolve root window if a widget is passed instead of a window
        if not isinstance(parent, Gtk.Window):
            parent = parent.get_root()
        self.set_transient_for(parent)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_default_size(300, 320)
        
        # English: Main vertical box container
        # Español: Contenedor de caja vertical principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_margin_top(40)
        main_box.set_margin_bottom(40)
        main_box.set_margin_start(40)
        main_box.set_margin_end(40)
        
        # English: Large activity spinner
        # Español: Indicador de actividad (spinner) grande
        spinner = Gtk.Spinner()
        spinner.set_size_request(80, 80)
        spinner.start()
        main_box.append(spinner)
        
        # English: Status label
        # Español: Etiqueta de estado
        self.label = Gtk.Label(label=message)
        self.label.add_css_class("title-label")
        self.label.set_wrap(True)
        self.label.set_max_width_chars(25)
        self.label.set_justify(Gtk.Justification.CENTER)
        main_box.append(self.label)
        
        # English: Optional action button to skip details and install directly
        # Español: Botón de acción opcional para saltar detalles e instalar directamente
        if skip_callback:
            skip_btn = Gtk.Button(label=_("Instalar directamente"))
            skip_btn.add_css_class("suggested-action")
            skip_btn.set_margin_top(12)
            skip_btn.connect("clicked", lambda btn: self._on_skip_clicked(skip_callback))
            main_box.append(skip_btn)
            
        self.set_content(main_box)

    def _on_skip_clicked(self, skip_callback):
        # English: Close progress window and trigger skip callback
        # Español: Cerrar la ventana de progreso y disparar el callback de salto
        self.close()
        skip_callback()

    def update_message(self, message):
        self.label.set_text(message)

