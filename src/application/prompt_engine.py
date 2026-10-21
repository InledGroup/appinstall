import codecs
import os
import re
import select
import signal
import subprocess
import threading
import time

# English: Detects and answers interactive questions made by package managers.
# When pacman/apt/dpkg ask something and there is no terminal, the process
# stalls waiting for input and the operation fails. This module watches the
# process output, notices when it is waiting for an answer and delegates the
# question to the UI (or to a fallback) through the ask_user callback.
# Español: Detecta y responde preguntas interactivas de los gestores de
# paquetes. Cuando pacman/apt/dpkg preguntan algo y no hay terminal, el
# proceso se queda esperando y la operación falla. Este módulo vigila la
# salida del proceso, detecta cuándo está esperando respuesta y delega la
# pregunta en la interfaz (o en un valor por defecto) vía el callback ask_user.

# English: Seconds of silence with pending text before suspecting a question
# Español: Segundos de silencio con texto pendiente antes de sospechar pregunta
PROMPT_IDLE = 0.4
# English: Extra patience for generic questions (log lines can end with '?')
# Español: Paciencia extra para preguntas genéricas (las líneas de registro
# también pueden terminar en '?')
GENERIC_IDLE = 1.5
# English: Silence before giving up on a question we cannot answer
# Español: Silencio antes de rendirse ante una pregunta que no sabemos responder
UNSUPPORTED_IDLE = 3.0
# English: Maximum number of yes/no questions answered in a single run
# Español: Máximo de preguntas sí/no respondidas en una sola ejecución
MAX_PROMPTS = 8
# English: Maximum characters of the question shown to the user
# Español: Máximo de caracteres de la pregunta que se muestra al usuario
MAX_QUESTION_LEN = 600

_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]')
# English: [Y/n], (y/N), [S/n], [s/N], (Sí/No), (Yes/No)...
# Español: [Y/n], (y/N), [S/n], [s/N], (Sí/No), (Yes/No)...
_YN_RE = re.compile(
    r'[\[(]\s*(?P<yes>[Yy](?:es)?|[Ss](?:[ií])?)\s*/\s*(?P<no>[Nn](?:o)?)\s*[\])]',
    re.IGNORECASE
)
_PASSWORD_RE = re.compile(r'(password|passwd|contraseñ|contrasen|\[sudo\] password)', re.IGNORECASE)
_MENU_RE = re.compile(
    r'(please select|select an option|choose an option|enter the number|enter your choice'
    r'|enter (a |an |the )?\w+|type (yes|no|the)|introduzca|introduce el n[uú]mero'
    r'|seleccione|selecciona|elige una|opción\s*:|option\s*:'
    r'|^\s*\d+\)\s+\S)',
    re.IGNORECASE | re.MULTILINE
)
_SPANISH_RE = re.compile(r'[¿]|desea|deseas|quieres|continuar|instalar|eliminar|actualizar|reemplazar')

# English: Handler registered by the UI: fn(question, default_yes, yes, no) -> bool|None
# Español: Callback registrado por la interfaz: fn(pregunta, por_defecto_sí, sí, no)
_prompt_handler = None

# English: Last failed command, kept so the UI can offer "open in a terminal"
# Español: Último comando fallido, para que la interfaz ofrezca «abrir en terminal»
_last_failure = None


def set_prompt_handler(handler):
    # English: Register the function used to ask the user yes/no questions
    # Español: Registrar la función que pregunta sí/no al usuario
    global _prompt_handler
    _prompt_handler = handler


def record_failure(cmd, env):
    # English: Remember the command that failed so it can be rerun in a terminal
    # Español: Recordar el comando fallido para poder relanzarlo en una terminal
    global _last_failure
    _last_failure = (list(cmd), dict(env) if env else None)


def clear_failure():
    # English: Forget any previously failed command (last run succeeded)
    # Español: Olvidar el comando fallido (la última ejecución ha ido bien)
    global _last_failure
    _last_failure = None


def get_last_failure():
    # English: Return (cmd, env) of the last failed command or None
    # Español: Devolver (cmd, env) del último comando fallido o None
    return _last_failure


def strip_ansi(text):
    return _ANSI_RE.sub('', text)


def classify_prompt(text):
    """Classify a stall as a question we can answer or not.

    Returns None (not a question), {'kind': 'yn', ...} for a two-option
    question, or {'kind': 'unsupported'} for passwords and menus.
    """
    # Español: Clasifica una parada como pregunta respondible o no.
    # Devuelve None (no es pregunta), {'kind': 'yn', ...} para una pregunta
    # de dos opciones o {'kind': 'unsupported'} para contraseñas y menús.
    clean = strip_ansi(text).strip()
    if not clean:
        return None

    match = _YN_RE.search(clean)
    if match:
        yes = match.group('yes')[0]
        no = match.group('no')[0]
        # English: The capital letter marks the default answer
        # Español: La letra en mayúscula marca la respuesta por defecto
        return {'kind': 'yn', 'yes': yes.lower(), 'no': no.lower(),
                'default_yes': yes.isupper()}

    if _PASSWORD_RE.search(clean):
        return {'kind': 'unsupported'}
    if _MENU_RE.search(clean):
        return {'kind': 'unsupported'}

    # English: Plain question without an explicit option marker
    # Español: Pregunta directa sin marcador de opciones explícito
    last_line = clean.splitlines()[-1].strip()
    if last_line.endswith(('?', '¿')) or clean.endswith(('?', '¿')):
        spanish = bool(_SPANISH_RE.search(clean))
        return {'kind': 'yn', 'yes': 's' if spanish else 'y', 'no': 'n',
                'default_yes': True}
    return None


def clean_question(text):
    # English: Compact the pending output into something readable for a dialog
    # Español: Compactar la salida pendiente en algo legible para un diálogo
    clean = strip_ansi(text)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    question = '\n'.join(lines[-8:])
    if len(question) > MAX_QUESTION_LEN:
        question = question[:MAX_QUESTION_LEN] + '…'
    return question


def ask_prompt(question, default_yes, yes_letter, no_letter):
    # English: Ask through the registered handler, falling back to the default
    # Español: Preguntar mediante el handler registrado, con valor por defecto
    handler = _prompt_handler
    if handler is None:
        return default_yes
    try:
        result = handler(question, default_yes, yes_letter, no_letter)
    except Exception:
        return default_yes
    if result is None:
        return default_yes
    return bool(result)


def _answer(process, letter):
    # English: Write the answer to the child's stdin so it can continue
    # Español: Escribir la respuesta en la stdin del proceso hijo para que siga
    try:
        process.stdin.write((letter + '\n').encode('utf-8'))
        process.stdin.flush()
        return True
    except Exception:
        return False


def _terminate(process):
    # English: Stop the process and its group, closing stdin first so helpers
    # waiting for input (sudo, pacman) get EOF instead of hanging forever
    # Español: Detener el proceso y su grupo, cerrando antes la stdin para que
    # los ayudantes que esperan entrada reciban EOF y no se queden colgados
    try:
        process.stdin.close()
    except Exception:
        pass
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except Exception:
            try:
                process.terminate() if sig == signal.SIGTERM else process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=5)
            return
        except Exception:
            continue


class CancelToken:
    """Permite cancelar un comando en curso desde la interfaz.

    English: Shared token used to stop a running command from the UI. The
    token is safe to use from another thread: cancelling it terminates the
    process group of the command that is currently running.
    Español: Token compartido para detener un comando en curso desde la
    interfaz. Es seguro usarlo desde otro hilo: al cancelarlo se termina el
    grupo de procesos del comando que esté en marcha.
    """

    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._process = None
        self._terminated = False

    def is_cancelled(self):
        """Devuelve True si el usuario ya pidió cancelar la operación."""
        return self._event.is_set()

    def was_terminated(self):
        """Devuelve True si el proceso llegó a ser detenido de verdad.

        English: A cancellation can be requested too late, when the command
        had already finished. This tells if the process was really killed.
        Español: Se puede pedir la cancelación demasiado tarde, cuando el
        comando ya había terminado. Esto indica si el proceso llegó a ser
        detenido de verdad.
        """
        with self._lock:
            return self._terminated

    def cancel(self):
        """Marca la operación como cancelada y detiene el proceso en marcha."""
        process = None
        terminate = False
        with self._lock:
            self._event.set()
            process = self._process
            if process is not None:
                try:
                    alive = process.poll() is None
                except Exception:
                    alive = True
                if alive:
                    self._terminated = True
                    terminate = True
        if terminate:
            _terminate(process)

    def attach(self, process):
        """Registra el proceso en marcha; si ya se canceló, lo detiene."""
        with self._lock:
            self._process = process
            already_cancelled = self._event.is_set()
            if already_cancelled:
                self._terminated = True
        if already_cancelled:
            _terminate(process)

    def detach(self, process):
        """Olvida el proceso en marcha (ya terminó)."""
        with self._lock:
            if self._process is process:
                self._process = None


def run_command(cmd, env=None, on_log=None, ask_user=None, timeout=None, cancel_token=None):
    """Run `cmd` with its stdin connected to a pipe so package manager
    questions can be answered.

    Returns (returncode, log_lines, blocked_question). `blocked_question` is
    only set when the process waited for an answer we cannot give (password,
    option menu...); in that case the process is stopped and the UI can offer
    to reopen the command in a real terminal. When `cancel_token` is given and
    the user cancels it, the process is stopped and the function returns.
    """
    # Español: Ejecuta `cmd` con la stdin conectada a una tubería para poder
    # responder las preguntas del gestor de paquetes. Devuelve
    # (codigo_salida, lineas_registro, pregunta_bloqueante).
    ask = ask_user or ask_prompt
    process = subprocess.Popen(
        cmd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, bufsize=0, start_new_session=True
    )

    if cancel_token is not None:
        cancel_token.attach(process)

    log_lines = []

    def record(line):
        if line.strip():
            log_lines.append(line)
            if on_log:
                try:
                    on_log(line)
                except Exception:
                    pass

    fd = process.stdout.fileno()
    decoder = codecs.getincrementaldecoder('utf-8')('replace')
    text_buf = ''
    # English: Last complete line emitted; some tools write the question
    # followed by a newline (zypper, python scripts...), so we also check it
    # Español: última línea completa emitida; algunas herramientas escriben
    # la pregunta seguida de un salto de línea (zypper, scripts...)
    last_line = ''
    last_data = time.monotonic()
    started = last_data
    prompts_asked = 0
    blocked = None

    try:
        while True:
            if cancel_token is not None and cancel_token.is_cancelled():
                # English: The user asked to stop: kill the process group
                # Español: El usuario pidió parar: mata el grupo de procesos
                _terminate(process)
                break

            if timeout and (time.monotonic() - started) > timeout:
                _terminate(process)
                break

            readable, _, _ = select.select([fd], [], [], 0.2)
            if readable:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    # English: End of output, drain what is left and leave
                    # Español: Fin de la salida, drenar lo que quede y salir
                    if text_buf.strip():
                        record(text_buf.rstrip('\r'))
                    break
                text_buf += decoder.decode(chunk)
                while '\n' in text_buf:
                    line, text_buf = text_buf.split('\n', 1)
                    line = line.rstrip('\r')
                    last_line = line
                    record(line)
                last_data = time.monotonic()
                continue

            # English: No new output: is the process waiting for an answer?
            # Español: No hay salida nueva: ¿está el proceso esperando respuesta?
            if process.poll() is not None:
                if text_buf.strip():
                    record(text_buf.rstrip('\r'))
                break

            # English: Candidate prompt: unfinished text, or the last complete
            # line when the question ended with a newline
            # Español: candidato a prompt: texto sin terminar, o la última
            # línea completa cuando la pregunta terminó con salto de línea
            candidate = text_buf
            if not candidate.strip():
                candidate = last_line
            pending = candidate.strip()
            if not pending:
                continue

            kind = classify_prompt(pending)
            if not kind:
                continue

            stall = time.monotonic() - last_data
            if kind['kind'] == 'yn' and prompts_asked < MAX_PROMPTS:
                idle_needed = PROMPT_IDLE if _YN_RE.search(pending) else GENERIC_IDLE
                if stall < idle_needed:
                    continue
                question = clean_question(pending)
                # English: Show the question in the log unless it was already
                # logged as a complete line (newline-terminated prompts)
                # Español: mostrar la pregunta en el registro salvo que ya se
                # haya registrado como línea completa (prompts con salto)
                if on_log and candidate is text_buf:
                    try:
                        on_log(question)
                    except Exception:
                        pass
                try:
                    yes = ask(question, kind['default_yes'], kind['yes'], kind['no'])
                except Exception:
                    yes = kind['default_yes']
                letter = kind['yes'] if yes else kind['no']
                if not _answer(process, letter):
                    break
                prompts_asked += 1
                # English: Clear the buffer so the same prompt is not asked twice
                # Español: Limpiar el buffer para no repetir la misma pregunta
                text_buf = ''
                last_line = ''
                last_data = time.monotonic()
            else:
                # English: Unsupported question, or too many questions answered
                # Español: Pregunta no soportada o demasiadas preguntas respondidas
                if stall < UNSUPPORTED_IDLE:
                    continue
                # English: A question we cannot answer: stop and let the UI
                # offer reopening the command in a terminal
                # Español: Pregunta que no sabemos responder: parar y dejar que
                # la interfaz ofrezca reabrir el comando en una terminal
                blocked = clean_question(pending)
                record(blocked)
                _terminate(process)
                break
    finally:
        if cancel_token is not None:
            cancel_token.detach(process)
        try:
            process.stdin.close()
        except Exception:
            pass
        try:
            process.stdout.close()
        except Exception:
            pass

    try:
        returncode = process.wait(timeout=10)
    except Exception:
        returncode = process.poll()
    return returncode, log_lines, blocked
