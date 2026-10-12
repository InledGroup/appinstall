import shlex
import shutil
import subprocess
import os

# English: Terminal emulators tried in order to reopen a failed command so the
# user can answer whatever question the package manager asks interactively.
# Español: Terminales que se prueban en orden para reabrir un comando fallido
# y que el usuario pueda responder la pregunta del gestor de paquetes.
_TERMINALS = [
    ('x-terminal-emulator', ['-e']),   # Debian/Ubuntu: gestor de alternativas
    ('gnome-terminal', ['--']),
    ('kgx', ['-e']),                   # GNOME Console
    ('konsole', ['-e']),
    ('xfce4-terminal', ['-x']),
    ('mate-terminal', ['-x']),
    ('tilix', ['-e']),
    ('alacritty', ['-e']),
    ('kitty', []),
    ('foot', ['-e']),
    ('xterm', ['-e']),
]

# English: Variables needed by the wrapper scripts (makepkg, AUR, apt) that
# must reach the shell inside the terminal.
# Español: Variables que necesitan los scripts auxiliares (makepkg, AUR, apt)
# y que deben llegar al shell de la terminal.
_FORWARD_ENV = (
    'SUDO', 'PACMAN', 'PACMAN_AUTH', 'APPINSTALL_SUDO',
    'DEBIAN_FRONTEND', 'LC_ALL', 'LANGUAGE', 'TERM',
)


def find_terminal():
    # English: Return (path, args) of the first available terminal or (None, None)
    # Español: Devolver (ruta, argumentos) de la primera terminal disponible o (None, None)
    for name, args in _TERMINALS:
        path = shutil.which(name)
        if path:
            return path, list(args)
    return None, None


def run_in_terminal(cmd, env=None):
    # English: Open a terminal running `cmd`, keeping it open to show the result
    # Español: Abrir una terminal con `cmd`, dejándola abierta para ver el resultado
    path, args = find_terminal()
    if not path or not cmd:
        return False

    env = env or dict(os.environ)
    exports = [f"{key}={env[key]}" for key in _FORWARD_ENV if key in env]

    inner = shlex.join(cmd)
    if exports:
        inner = 'env ' + ' '.join(shlex.quote(item) for item in exports) + ' ' + inner

    script = (
        f"{inner}\n"
        "rc=$?\n"
        "echo\n"
        "echo \"[AppInstall] código de salida: $rc\"\n"
        "printf 'Pulsa Intro para cerrar la ventana...'\n"
        "read _appinstall_tecla\n"
    )

    try:
        subprocess.Popen([path] + args + ['sh', '-c', script], start_new_session=True)
        return True
    except Exception:
        return False


def open_last_failure_in_terminal():
    # English: Relaunch the last failed command in a terminal (if any)
    # Español: Relanzar el último comando fallido en una terminal (si lo hay)
    from src.application import prompt_engine
    failure = prompt_engine.get_last_failure()
    if not failure:
        return False
    cmd, env = failure
    return run_in_terminal(cmd, env)
