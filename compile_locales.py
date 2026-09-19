import os

# English: Compile PO translation file to MO binary format
# Español: Compilar el archivo de traducción PO al formato binario MO
def compile_po(po_file, mo_file):
    try:
        import polib
        po = polib.pofile(po_file)
        po.save_as_mofile(mo_file)
        print("Compiled using polib")
    except ImportError:
        import subprocess
        # English: Fallback to GNU gettext's msgfmt command line utility
        # Español: Alternativa al utilitario de línea de comandos msgfmt de GNU gettext
        try:
            subprocess.run(['msgfmt', '-o', mo_file, po_file], check=True)
            print("Compiled using msgfmt")
        except Exception as e:
            print(f"Error compiling locales with msgfmt: {e}")
            raise e


if __name__ == "__main__":
    po_path = 'locale/en/LC_MESSAGES/appinstall.po'
    mo_path = 'locale/en/LC_MESSAGES/appinstall.mo'
    if os.path.exists(po_path):
        print(f"Compiling {po_path} to {mo_path}...")
        compile_po(po_path, mo_path)
        # Also copy to the appinstall structure
        dest_mo1 = 'appinstall/usr/share/locale/en/LC_MESSAGES/appinstall.mo'
        dest_mo2 = 'appinstall/usr/share/appinstall/locale/en/LC_MESSAGES/appinstall.mo'
        import shutil
        os.makedirs(os.path.dirname(dest_mo1), exist_ok=True)
        shutil.copy(mo_path, dest_mo1)
        os.makedirs(os.path.dirname(dest_mo2), exist_ok=True)
        shutil.copy(mo_path, dest_mo2)
        print("Done.")
    else:
        print(f"File {po_path} not found.")
