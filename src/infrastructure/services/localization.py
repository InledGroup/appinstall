import os
import locale
import gettext

def setup_localization():
    # Buscar el directorio de traducciones en las ubicaciones habituales
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    locale_dirs = [
        os.path.join(base, 'locale'),                             # Desarrollo desde el repositorio
        os.path.join(base, 'appinstall/usr/share/appinstall/locale'),  # Copia incluida en el repo
        '/app/share/appinstall/locale',                           # Flatpak
        '/app/share/locale',                                      # Flatpak genérico
        '/usr/share/appinstall/locale',                           # Instalación de sistema
        '/usr/share/locale',                                      # Sistema genérico
    ]
    LOCALE_DIR = next((d for d in locale_dirs if os.path.isdir(d)), locale_dirs[0])

    try:
        locale.setlocale(locale.LC_ALL, '')
    except:
        pass

    try:
        gettext.bindtextdomain('appinstall', LOCALE_DIR)
        gettext.textdomain('appinstall')
    except Exception:
        pass
    return gettext.gettext

_ = setup_localization()
