"""Barra inferior de operaciones en curso.

Cada operación (instalación, desinstalación, análisis, limpieza...) ocupa
una fila propia con su propia barra de progreso. De este modo varias
operaciones simultáneas conviven en la interfaz sin cancelarse entre sí.

English: Bottom bar that keeps one row per running operation, so several
concurrent processes can be tracked at the same time.
"""

from gi.repository import Gtk, GLib, Pango
from src.infrastructure.services.localization import _


class OperationRow(Gtk.Box):
    """Fila que representa una operación en curso.

    La barra de progreso rebota de forma continua gracias a un temporizador
    propio: no depende de que el proceso escriba en la salida, así que
    sigue animándose aunque la operación tarde mucho en responder.
    """

    # Milisegundos entre dos pulsos. GTK4 detiene la animación del bloque
    # si no se llama a pulse() con regularidad, de ahí el temporizador.
    PULSE_INTERVAL = 100

    def __init__(self, op_id, title, skip_callback=None, cancel_callback=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.op_id = op_id
        self.skip_callback = skip_callback
        self.cancel_callback = cancel_callback
        self._pulse_source = 0
        self._done = False

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_row.set_valign(Gtk.Align.CENTER)

        self.spinner = Gtk.Spinner()
        self.spinner.set_size_request(14, 14)
        top_row.append(self.spinner)

        self.title_label = Gtk.Label(label=title, xalign=0)
        self.title_label.add_css_class("status-title-label")
        top_row.append(self.title_label)

        self.log_label = Gtk.Label(label="", xalign=0)
        self.log_label.add_css_class("status-log-label")
        self.log_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.log_label.set_hexpand(True)
        top_row.append(self.log_label)

        self.skip_button = Gtk.Button(label=_("Omitir"))
        self.skip_button.add_css_class("flat")
        self.skip_button.set_visible(skip_callback is not None)
        if skip_callback is not None:
            self.skip_button.connect("clicked", self._on_skip_clicked)
        top_row.append(self.skip_button)

        # English: Stop button, only shown for operations that can be stopped
        # Español: Botón de parar, visible solo en operaciones que se pueden detener
        self.cancel_button = Gtk.Button()
        self.cancel_button.set_icon_name("process-stop-symbolic")
        self.cancel_button.add_css_class("flat")
        self.cancel_button.set_tooltip_text(_("Cancelar operación"))
        self.cancel_button.set_visible(cancel_callback is not None)
        if cancel_callback is not None:
            self.cancel_button.connect("clicked", self._on_cancel_clicked)
        top_row.append(self.cancel_button)

        self.append(top_row)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("bottom-progress-bar")
        self.append(self.progress_bar)

    def _on_skip_clicked(self, _button):
        if self.skip_callback:
            self.skip_callback()

    def _on_cancel_clicked(self, _button):
        if self.cancel_callback:
            self.cancel_callback()

    def set_cancelling(self):
        """Marca la fila como cancelándose: el botón deja de ser utilizable."""
        self.cancel_button.set_sensitive(False)
        self.cancel_button.set_visible(False)
        self.skip_button.set_visible(False)

    def start(self):
        """Arranca la animación de la fila."""
        self.spinner.start()
        self.progress_bar.pulse()
        self._start_pulsing()

    def _start_pulsing(self):
        if self._pulse_source:
            return

        def _tick():
            if self._done:
                return False
            # La barra sigue rebotando aunque el proceso no escriba nada.
            self.progress_bar.pulse()
            return True

        self._pulse_source = GLib.timeout_add(self.PULSE_INTERVAL, _tick)

    def stop(self):
        """Detiene la animación de la fila."""
        self._done = True
        if self._pulse_source:
            GLib.source_remove(self._pulse_source)
            self._pulse_source = 0
        self.spinner.stop()

    def set_log(self, line):
        """Muestra la última línea del registro de la operación."""
        if line is None:
            return
        text = str(line).strip()
        if not text:
            return
        self.log_label.set_text(text)

    def set_title(self, text):
        self.title_label.set_text(text)


class OperationBar(Gtk.Box):
    """Contenedor de la barra inferior con una fila por operación activa."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("bottom-status-bar")
        self.set_visible(False)
        self._rows = {}
        self._next_id = 1

    def start(self, title, skip_callback=None, cancel_callback=None):
        """Crea una operación nueva y devuelve su identificador."""
        op_id = self._next_id
        self._next_id += 1

        row = OperationRow(op_id, title, skip_callback=skip_callback,
                           cancel_callback=cancel_callback)
        self._rows[op_id] = row
        self.append(row)
        row.start()
        self.set_visible(True)
        return op_id

    def get_row(self, op_id):
        return self._rows.get(op_id)

    def set_log(self, op_id, line):
        row = self._rows.get(op_id)
        if row is not None:
            row.set_log(line)

    def set_title(self, op_id, text):
        row = self._rows.get(op_id)
        if row is not None:
            row.set_title(text)

    def finish(self, op_id):
        """Elimina una operación de la barra."""
        row = self._rows.pop(op_id, None)
        if row is None:
            return
        row.stop()
        self.remove(row)
        if not self._rows:
            self.set_visible(False)

    def finish_all(self):
        """Elimina todas las operaciones de la barra."""
        for op_id in list(self._rows.keys()):
            self.finish(op_id)

    def has_operations(self):
        return bool(self._rows)
