from gi.repository import Gtk, Adw

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
