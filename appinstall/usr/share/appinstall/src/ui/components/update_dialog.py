from gi.repository import Adw
from src.infrastructure.services.localization import _
from src.utils.constants import CURRENT_VERSION

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
