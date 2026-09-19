import os
import locale
import gettext

def setup_localization():
    # Buscar el directorio de traducciones en las ubicaciones habituales
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    locale_dirs = [
        os.path.join(base, 'locale'),                             # Desarrollo desde el repositorio
        os.path.join(base, 'appinstall/usr/share/appinstall/locale'),  # Copia incluida en el repo
        os.path.join(base, 'appinstall/usr/share/locale'),        # Copia estándar en el repo
        '/app/share/appinstall/locale',                           # Flatpak
        '/app/share/locale',                                      # Flatpak genérico
        '/usr/share/appinstall/locale',                           # Instalación de sistema
        '/usr/share/locale',                                      # Sistema genérico
    ]
    LOCALE_DIR = next((d for d in locale_dirs if os.path.isdir(d)), locale_dirs[0])

    try:
        locale.setlocale(locale.LC_ALL, '')
    except Exception:
        pass

    # Determinar idioma del entorno
    lang_env = os.environ.get('LANGUAGE') or os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    lang_clean = lang_env.split('.')[0].split(':')[0].strip()

    # Si el sistema está en español, los textos del código fuente ya son en español
    if lang_clean.lower().startswith('es'):
        try:
            trans = gettext.translation('appinstall', LOCALE_DIR, languages=['es'], fallback=True)
            return trans.gettext
        except Exception:
            return gettext.gettext

    # Para inglés o cualquier otro idioma no español (fr, de, it, ja, C, etc.):
    # Intentar el idioma específico si existe catálogo, y siempre hacer fallback a 'en' (inglés)
    languages = []
    if lang_clean:
        languages.append(lang_clean)
        lang_short = lang_clean.split('_')[0]
        if lang_short not in languages:
            languages.append(lang_short)
    if 'en' not in languages:
        languages.append('en')

    for loc_dir in locale_dirs:
        if os.path.isdir(loc_dir):
            try:
                trans = gettext.translation('appinstall', loc_dir, languages=languages, fallback=False)
                if trans:
                    return trans.gettext
            except Exception:
                continue

    return gettext.gettext

_ = setup_localization()

