import os
import locale
import gettext

def setup_localization():
    # Configurar localización
    LOCALE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'locale')
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
    return gettext.gettext

_ = setup_localization()
