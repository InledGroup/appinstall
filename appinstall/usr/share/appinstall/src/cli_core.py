import sys
import subprocess
import shutil
import os
import threading
import time
from typing import Optional, List, Dict, Tuple

from src.config import CLI_NAME


# ── Colors ──────────────────────────────────────────────────────────────────

# ANSI escape codes for terminal text coloring.
# Keys are human-readable names; values are raw SGR (Select Graphic Rendition) sequences.
# These are only applied when stdout is a real TTY — see _c().
_COLORS = {
    'reset':   '\033[0m',
    'bold':    '\033[1m',
    'dim':     '\033[2m',
    'cyan':    '\033[36m',
    'green':   '\033[32m',
    'yellow':  '\033[33m',
    'magenta': '\033[35m',
    'blue':    '\033[34m',
    'red':     '\033[31m',
    'white':   '\033[97m',
    'gray':    '\033[90m',
}

# Global parseable mode flag. When True, output is plain text without ANSI
# styles, formatted for easy machine parsing (tab-separated fields).
PARSEABLE = False

def _c(color: str, text: str) -> str:
    """Wrap *text* in an ANSI color escape sequence, or return plain text if stdout is not a TTY.
    
    - If sys.stdout.isatty() is False (e.g. piped output), colors are suppressed.
    - If PARSEABLE mode is active, colors are always suppressed.
    - Falls back to plain text so logs/redirections stay clean.
    - Uses _COLORS.get() with a fallback to '' so unknown color names silently degrade.
    """
    if PARSEABLE or not sys.stdout.isatty():
        return text
    return f"{_COLORS.get(color, '')}{text}{_COLORS['reset']}"


# ── Spinner ─────────────────────────────────────────────────────────────────

# Braille spinner frames used for animated progress indication on TTYs.
# The sequence simulates a clockwise rotation.
_SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

class Spinner:
    """Context manager that displays an animated CLI spinner while a task runs.
    
    Usage:
        with Spinner("Searching..."):
            do_work()
    
    Behaviour:
    - On a TTY: starts a daemon thread that writes animated frames to stdout via \r.
    - On a non-TTY (pipe/file): prints a single static line instead.
    - On exit: clears the spinner line with \\r\\033[K so next output starts clean.
    - In PARSEABLE mode: the spinner is completely suppressed.
    """
    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread = None
        self._is_tty = not PARSEABLE and sys.stdout.isatty()

    def __enter__(self):
        if self._is_tty:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        elif not PARSEABLE:
            print(f"  {self.message}...")
        return self

    def __exit__(self, *args):
        if self._is_tty:
            self._stop.set()
            if self._thread:
                self._thread.join(timeout=2)
            try:
                sys.stdout.write('\r\033[K')
                sys.stdout.flush()
            except Exception:
                pass

    def _run(self):
        i = 0
        while not self._stop.is_set():
            char = _SPINNER_CHARS[i % len(_SPINNER_CHARS)]
            try:
                sys.stdout.write(f"\r  \033[36m{char}\033[0m {self.message}...")
                sys.stdout.flush()
            except Exception:
                break
            self._stop.wait(0.08)
            i += 1


def _progress_update(message: str, is_tty: bool):
    """Write a progress line that overwrites itself."""
    if is_tty:
        sys.stdout.write(f"\r  \033[36m⠋\033[0m {message}")
        sys.stdout.flush()


def _progress_clear(is_tty: bool):
    """Clear the progress line."""
    if is_tty:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


class _LiveSpinner:
    """Animated spinner that runs in its own thread.
    
    Other threads call update() to change the displayed message.
    The spinner thread independently cycles through braille frames.
    """
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._status = ""
        self._lock = threading.Lock()

    def start(self, initial_message: str = ""):
        self._status = initial_message
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, message: str):
        with self._lock:
            self._status = message

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        try:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        except Exception:
            pass

    def _run(self):
        i = 0
        while not self._stop.is_set():
            with self._lock:
                msg = self._status
            char = _SPINNER_CHARS[i % len(_SPINNER_CHARS)]
            try:
                sys.stdout.write(f"\r  \033[36m{char}\033[0m {msg}")
                sys.stdout.flush()
            except Exception:
                break
            self._stop.wait(0.08)
            i += 1




# ── Adapters ────────────────────────────────────────────────────────────────

def _get_adapters():
    """Discover and return a dict of available package adapters.
    
    Returns:
        dict[str, object] — keyed by source name ('system', 'flatpak', 'snap', 'aur', 'pulsar').
        Only adapters whose backend is actually installed on the machine are included.
    
    Resolution order:
    1. The system adapter (apt/dnf/pacman/etc.) from the factory — always included.
    2. FlatpakAdapter — only if `flatpak` is on PATH (is_available()).
    3. SnapAdapter — only if `snap` is on PATH.
    4. AurAdapter — only if `pacman` is on PATH (AUR helpers depend on pacman).
    5. PulsarStoreAdapter — always available (remote catalog).
    """
    from src.infrastructure.adapters.factory import get_package_manager
    from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
    from src.infrastructure.adapters.snap_adapter import SnapAdapter
    from src.infrastructure.adapters.aur_adapter import AurAdapter
    from src.infrastructure.adapters.brew_adapter import BrewAdapter
    from src.infrastructure.adapters.pulsar_store_adapter import PulsarStoreAdapter

    pm = get_package_manager()
    adapters = {'system': pm}

    fp = FlatpakAdapter()
    if fp.is_available():
        adapters['flatpak'] = fp

    sn = SnapAdapter()
    if sn.is_available():
        adapters['snap'] = sn

    if shutil.which('pacman'):
        adapters['aur'] = AurAdapter()

    br = BrewAdapter()
    if br.is_available():
        adapters['brew'] = br

    # Pulsar Store is always available (remote catalog)
    adapters['pulsar'] = PulsarStoreAdapter()

    return adapters


# Maps source names to (short_label, colored_label) pairs.
# The short label is used as a compact identifier (e.g. 'sys', 'fpk').
# The colored label is the same string wrapped in ANSI codes for terminal display.
SOURCE_LABELS = {
    'system':  ('sys', _c('blue',   'sys')),
    'flatpak': ('fpk', _c('green',  'fpk')),
    'snap':    ('snap', _c('magenta', 'snap')),
    'aur':     ('aur', _c('yellow', 'aur')),
    'brew':    ('brew', _c('magenta', 'brew')),
    'pulsar':  ('psr', _c('cyan',   'psr')),
}

# Aliases: maps user-friendly names to canonical source keys
SOURCE_ALIASES = {
    'flatpak': 'flatpak', 'flathub': 'flatpak', 'fpk': 'flatpak',
    'system': 'system', 'sys': 'system', 'pacman': 'system',
    'apt': 'system', 'dnf': 'system', 'yum': 'system', 'apt-get': 'system',
    'snap': 'snap', 'snapcraft': 'snap',
    'aur': 'aur', 'yay': 'aur', 'paru': 'aur',
    'brew': 'brew', 'homebrew': 'brew', 'linuxbrew': 'brew',
    'pulsar': 'pulsar', 'store': 'pulsar', 'pulsar-store': 'pulsar',
    'psr': 'pulsar',
}


def _normalize_source(name: str) -> str:
    """Resolve a source name or alias to its canonical key.
    
    Examples:
        _normalize_source("flathub")  -> "flatpak"
        _normalize_source("sys")      -> "system"
        _normalize_source("pacman")   -> "system"
        _normalize_source("homebrew") -> "brew"
        _normalize_source("unknown")  -> "unknown" (passthrough)
    """
    if not name:
        return name
    return SOURCE_ALIASES.get(name.lower(), name.lower())


def _parse_source(query: str):
    """Parse an optional source prefix from a package query.
    
    Supported prefixes: flatpak:, snap:, aur:, pacman:, brew:, pulsar:
    
    Returns:
        (source_name_or_None, stripped_query)
    
    Examples:
        _parse_source("flatpak:org.gimp.GIMP")  -> ("flatpak", "org.gimp.GIMP")
        _parse_source("pulsar:sayri-gateway-tg") -> ("pulsar", "sayri-gateway-tg")
        _parse_source("firefox")                 -> (None, "firefox")
    """
    for prefix in ['flatpak:', 'snap:', 'aur:', 'pacman:', 'brew:', 'pulsar:']:
        if query.lower().startswith(prefix):
            return prefix.rstrip(':'), query[len(prefix):]
    return None, query


def _generate_search_variations(query: str) -> List[str]:
    """Generate smart variations of a search query to improve fuzzy matching.
    
    Takes a multi-word query and produces the original, hyphenated, and
    concatenated forms so adapters can match against different naming conventions.
    
    Examples:
        "wl clipboard" -> ["wl clipboard", "wl-clipboard", "wlclipboard"]
        "visual studio code" -> ["visual studio code", "visual-studio-code", "visualstudiocode"]
    
    Returns a deduplicated list (preserving insertion order via dict.fromkeys).
    Single-word queries are returned as-is.
    """
    variations = [query]
    if ' ' in query:
        variations.append(query.replace(' ', '-'))
        variations.append(query.replace(' ', ''))
    return list(dict.fromkeys(variations))


def _run_cmd(cmd, timeout=120):
    """Execute an external command and stream its output live.
    
    Args:
        cmd: List of command arguments (passed to subprocess.Popen).
        timeout: Maximum wall-clock seconds before the process is killed (default 120).
    
    Returns:
        True if the process exited with code 0, False otherwise.
    
    Behaviour:
    - stdout and stderr are merged (stderr=STDOUT) and printed line-by-line as they arrive.
    - On TimeoutExpired, the process is killed and an error is printed to stderr.
    - Any other exception (e.g. FileNotFoundError) is caught and printed.
    """
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        for line in proc.stdout:
            print(line, end='')
        proc.wait(timeout=timeout)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        print(_c('red', "Timed out."), file=sys.stderr)
        return False
    except Exception as e:
        print(_c('red', f"Error: {e}"), file=sys.stderr)
        return False


def _run_search_with_progress(adapters: dict, query: str, variations: List[str]) -> Dict[str, list]:
    """Search all adapters in parallel with animated spinner.
    
    Returns results grouped by source, with progress updates as each
    source completes.
    """
    import concurrent.futures

    is_tty = not PARSEABLE and sys.stdout.isatty()
    total = len(adapters)
    done_count = [0]
    done_lock = threading.Lock()
    spinner = _LiveSpinner()

    def search_one(source_name, adapter):
        seen = set()
        all_results = []
        for variation in variations:
            try:
                results = adapter.search(variation)
            except Exception:
                results = []
            for r in results:
                name = r.get('name', '')
                if name not in seen:
                    seen.add(name)
                    all_results.append(r)
        with done_lock:
            done_count[0] += 1
            count = done_count[0]
        if is_tty:
            spinner.update(f"Searching ({count}/{total}) {source_name}...")
        return source_name, all_results

    if is_tty:
        spinner.start(f"Searching (0/{total})...")

    results_by_source = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(total, 4)) as pool:
        futures = {pool.submit(search_one, src, adv): src for src, adv in adapters.items()}
        for future in concurrent.futures.as_completed(futures):
            try:
                source_name, results = future.result()
                results_by_source[source_name] = results
            except Exception:
                src = futures[future]
                results_by_source[src] = []

    spinner.stop()
    return results_by_source


# ── Format helpers ──────────────────────────────────────────────────────────

def _print_search_results(results_by_source: Dict[str, list], query: str):
    """Print search results grouped by source with nice formatting.
    
    Each source section shows a colored label header, a divider line,
    and each package result with its name and truncated description.
    
    In PARSEABLE mode, outputs tab-separated lines: name<TAB>source<TAB>description
    
    If there are no results, a "No results" message is shown instead.
    """
    total = sum(len(r) for r in results_by_source.values())
    if total == 0:
        if PARSEABLE:
            return
        print(_c('dim', f"  No results for ") + _c('bold', f"'{query}'"))
        return

    if PARSEABLE:
        for source, results in results_by_source.items():
            for r in results:
                name = r.get('name', '')
                desc = r.get('desc', '')
                print(f"{name}\t{source}\t{desc}")
        return

    print(_c('dim', f"  Found ") + _c('bold', str(total)) + _c('dim', f" results for ") + _c('bold', f"'{query}'"))
    print()

    for source, results in results_by_source.items():
        if not results:
            continue
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('bold', colored_label)}  {_c('dim', f'({len(results)} packages)')}")
        print(f"  {_c('dim', '─' * 50)}")
        for r in results:
            name = r.get('name', '')
            desc = r.get('desc', '')
            print(f"    {_c('white', name)}")
            if desc:
                if len(desc) > 70:
                    desc = desc[:67] + '...'
                print(f"    {_c('dim', desc)}")
        print()


def _print_installed_list(packages_by_source: Dict[str, list], query: str = None):
    """Print installed packages grouped by source.
    
    Each source section shows a colored label and the list of installed
    package names (sorted alphabetically). A total count is printed at the end.
    
    In PARSEABLE mode, outputs tab-separated lines: name<TAB>source
    
    If *query* is provided, the title reflects the filter (e.g. "Installed packages matching 'firefox'").
    """
    total = sum(len(p) for p in packages_by_source.values())

    if PARSEABLE:
        for source, packages in packages_by_source.items():
            for pkg in sorted(packages):
                print(f"{pkg}\t{source}")
        return

    title = f"Installed packages"
    if query:
        title += f" matching '{query}'"
    print(_c('bold', f"  {title}"))
    print(_c('dim', '  ─' * 25))
    print()

    for source, packages in packages_by_source.items():
        if not packages:
            continue
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('bold', colored_label)}  {_c('dim', f'({len(packages)} packages)')}")
        for pkg in sorted(packages):
            print(f"    {pkg}")
        print()

    print(_c('dim', '  Total: ') + _c('bold', str(total)) + _c('dim', ' packages'))


def _print_package_info(info: dict, source: str = None):
    """Print detailed package information in a structured card format.
    
    In PARSEABLE mode, outputs tab-separated key=value pairs.
    
    Fields displayed (if present in the info dict):
    - name (bold, white)
    - source (colored label)
    - version
    - description
    - developer
    - license
    - size
    """
    name = info.get('name', 'unknown')
    version = info.get('version', '')
    desc = info.get('description', '')
    size = info.get('size', '')
    developer = info.get('developer', '')
    license_ = info.get('license', '')

    if PARSEABLE:
        fields = [
            ('name', name),
            ('version', version),
            ('description', desc),
            ('source', source or ''),
            ('developer', developer),
            ('license', license_),
            ('size', size),
        ]
        for key, val in fields:
            if val:
                print(f"{key}={val}")
        return

    print()
    print(f"  {_c('bold', _c('white', name))}")
    if source:
        label, colored_label = SOURCE_LABELS.get(source, (source, source))
        print(f"  {_c('dim', 'source:')}  {colored_label}")
    if version:
        print(f"  {_c('dim', 'version:')} {_c('green', version)}")
    if desc:
        print(f"  {_c('dim', 'about:')}  {desc}")
    if developer:
        print(f"  {_c('dim', 'by:')}     {developer}")
    if license_:
        print(f"  {_c('dim', 'license:')} {license_}")
    if size:
        print(f"  {_c('dim', 'size:')}   {size}")
    print()


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_search(query: str):
    """Search for packages across all available adapters.
    
    Searches all adapters in parallel with live progress, then displays
    results grouped by source.
    
    Supports 'from' source filtering:
      sayri from pulsar  → search only in Pulsar Store
      gimp from flathub  → search only in Flatpak
    """
    if not query:
        print(f"  Usage: {_c('bold', f'{CLI_NAME} search <query>')}", file=sys.stderr)
        print(f"  Example: {_c('dim', f'{CLI_NAME} search wl clipboard')}", file=sys.stderr)
        return False

    # Check for 'from' syntax (e.g. 'sayri from pulsar')
    source_filter = None
    clean_query = query
    query_lower = query.lower()
    if ' from ' in query_lower:
        parts = query.rsplit(' from ', 1)
        if len(parts) == 2:
            possible_source = parts[1].strip().lower()
            normalized = _normalize_source(possible_source)
            all_adapters = _get_adapters()
            if normalized in all_adapters:
                source_filter = normalized
                clean_query = parts[0].strip()

    # Also support prefix syntax (flatpak:gimp, pulsar:sayri)
    if not source_filter:
        source_prefix, parsed_query = _parse_source(query)
        if source_prefix:
            normalized = _normalize_source(source_prefix)
            all_adapters = _get_adapters()
            if normalized in all_adapters:
                source_filter = normalized
                clean_query = parsed_query

    if source_filter:
        adapters = {source_filter: _get_adapters()[source_filter]}
    else:
        adapters = _get_adapters()

    variations = _generate_search_variations(clean_query)

    results_by_source = _run_search_with_progress(adapters, clean_query, variations)
    _print_search_results(results_by_source, clean_query)
    return any(results_by_source.values())


def cmd_list(filter_source: Optional[str] = None):
    """List all installed packages, optionally filtered by source.
    
    Queries all adapters in parallel with animated spinner.
    """
    import concurrent.futures

    adapters = _get_adapters()
    is_tty = not PARSEABLE and sys.stdout.isatty()
    total = len(adapters)
    done_count = [0]
    done_lock = threading.Lock()
    packages_by_source = {}
    spinner = _LiveSpinner()

    def load_one(source_name, adapter):
        try:
            packages = adapter.list_installed()
        except Exception:
            packages = []
        with done_lock:
            done_count[0] += 1
            count = done_count[0]
        if is_tty:
            spinner.update(f"Loading ({count}/{total}) {source_name}...")
        return source_name, packages

    if is_tty:
        spinner.start(f"Loading (0/{total})...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(total, 4)) as pool:
        futures = {}
        for source, adapter in adapters.items():
            if filter_source and source != filter_source:
                continue
            futures[pool.submit(load_one, source, adapter)] = source
        for future in concurrent.futures.as_completed(futures):
            try:
                source_name, packages = future.result()
                if packages:
                    packages_by_source[source_name] = packages
            except Exception:
                pass

    spinner.stop()
    _print_installed_list(packages_by_source)
    return True


def cmd_search_installed(query: str):
    """Search within installed packages (filter by substring match).
    
    Queries each adapter for installed packages, then filters locally
    with a case-insensitive substring check. Useful for finding whether
    a package is already installed without leaving the CLI.
    """
    if not query:
        print(f"  Usage: {_c('bold', f'{CLI_NAME} list <query>')}", file=sys.stderr)
        print(f"  Example: {_c('dim', f'{CLI_NAME} list firefox')}", file=sys.stderr)
        return False

    adapters = _get_adapters()
    query_lower = query.lower()
    packages_by_source = {}

    with Spinner(f"Searching installed for '{query}'"):
        for source, adapter in adapters.items():
            try:
                packages = adapter.list_installed()
                matched = [p for p in packages if query_lower in p.lower()]
                if matched:
                    packages_by_source[source] = matched
            except Exception:
                pass

    _print_installed_list(packages_by_source, query)
    return any(packages_by_source.values())


def cmd_install(packages):
    """Install one or more packages by name, source-prefixed name, or local file path.

    Accepts either:
      - A single string (legacy): "firefox"
      - A list of (name, source) tuples: [("gimp", "fpk"), ("vlc", "sys")]

    Resolution order per package:
    1. If *name* is an existing file path, delegate to _install_file().
    2. If *source* is specified, install from that specific source.
    3. If name has a prefix (e.g. flatpak:org.gimp.GIMP), install from that source.
    4. Otherwise, try each adapter in order:
       a. Check if the package (or a variation) is already installed — reinstall.
       b. Search the adapter for the query and install the first match.
    5. Fall back to the system adapter with the raw name.
    6. Report failure if nothing matched.

    Returns True if at least one package was installed successfully.
    """
    if isinstance(packages, str):
        packages = [(packages, None)]

    if not packages:
        print(f"  Usage: {_c('bold', f'{CLI_NAME} install <package>')}", file=sys.stderr)
        print(f"  Examples:", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} install firefox')}          {_c('dim', '# auto-detect source')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} install flatpak:org.gimp.GIMP')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} install snap:code')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} install /path/to/file.deb')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} install gimp vlc from flathub')}", file=sys.stderr)
        return False

    success = False
    for pkg_name, pkg_source in packages:
        if _install_single(pkg_name, pkg_source):
            success = True
    return success


def _install_aur(adapter, name: str) -> bool:
    """Install a package from the AUR, showing the PKGBUILD first and asking for confirmation."""
    print(f"  {_c('yellow', 'AUR')}  {_c('bold', name)}  {_c('dim', '· PKGBUILD')}")
    print(_c('dim', '  ' + '─' * 50))
    pkgbuild = ""
    try:
        pkgbuild = adapter.get_pkgbuild(name)
    except Exception as e:
        print(_c('red', f"  Error al obtener el PKGBUILD: {e}"), file=sys.stderr)

    if not pkgbuild:
        print(_c('red', "  No se pudo obtener el PKGBUILD."), file=sys.stderr)
        try:
            answer = input(_c('bold', "  ¿Instalar de todas formas? [s/N] "))
        except EOFError:
            answer = ""
    else:
        for line in pkgbuild.split('\n')[:120]:
            print(f"  {line}")
        total_lines = pkgbuild.count('\n')
        if total_lines > 120:
            print(_c('dim', f"  ... (PKGBUILD truncado, {total_lines} líneas)"))
        print(_c('dim', '  ' + '─' * 50))
        try:
            answer = input(_c('bold', f"  ¿Revisado el PKGBUILD? Instalar '{name}' desde AUR [s/N] "))
        except EOFError:
            answer = ""

    if answer.lower() not in ('s', 'si', 'y', 'yes'):
        print(_c('dim', "  Instalación cancelada."))
        return False

    print(f"  {_c('cyan', 'Building and installing')} {_c('bold', name)} {_c('dim', 'from AUR...')}")
    cmd = adapter.install(name)
    return _run_cmd(cmd)


def _install_single(package: str, source: str = None) -> bool:
    """Install a single package. Returns True on success."""
    if not package:
        return False

    if os.path.isfile(package):
        return _install_file(package)

    adapters = _get_adapters()

    if source and source in adapters:
        if source == 'aur':
            return _install_aur(adapters[source], package)
        cmd = adapters[source].install(package)
        print(f"  {_c('cyan', 'Installing')} {_c('bold', package)} {_c('dim', f'from {source}...')}")
        return _run_cmd(cmd)

    if not source:
        src, name = _parse_source(package)
        if src and src in adapters:
            if src == 'aur':
                return _install_aur(adapters[src], name)
            cmd = adapters[src].install(name)
            print(f"  {_c('cyan', 'Installing')} {_c('bold', name)} {_c('dim', f'from {src}...')}")
            return _run_cmd(cmd)
        package = name

    variations = _generate_search_variations(package)
    for src, adapter in adapters.items():
        try:
            installed = adapter.list_installed()
            for variation in variations:
                if variation in installed:
                    cmd = adapter.uninstall(variation)
                    print(f"  {_c('cyan', 'Installing')} {_c('bold', variation)} {_c('dim', f'from {src}...')}")
                    return _run_cmd(cmd)
            results = adapter.search(variations[0])
            if results and results[0].get('name') in variations:
                match_name = results[0]['name']
                if src == 'aur':
                    return _install_aur(adapter, match_name)
                cmd = adapter.install(match_name)
                print(f"  {_c('cyan', 'Installing')} {_c('bold', match_name)} {_c('dim', f'from {src}...')}")
                return _run_cmd(cmd)
        except Exception:
            pass

    if 'system' in adapters:
        cmd = adapters['system'].install(package)
        print(f"  {_c('cyan', 'Installing')} {_c('bold', package)} {_c('dim', 'from system repos...')}")
        return _run_cmd(cmd)

    print(_c('red', f"  Could not find '{package}' in any source."), file=sys.stderr)
    return False


def _install_file(file_path: str):
    """Install a local package file by detecting its format and dispatching to the right backend.
    
    Supported formats:
    - .deb        -> pkexec dpkg -i
    - .rpm        -> pkexec rpm -i
    - .pkg.tar.zst / .pkg.tar.xz -> pkexec pacman -U
    - .flatpakref / .flatpak     -> flatpak install (adapter or pkexec fallback)
    - .AppImage   -> copy to /usr/bin and chmod +x
    
    Returns True on success, False on failure or unknown type.
    """
    adapters = _get_adapters()

    if file_path.endswith('.deb') and 'system' in adapters:
        cmd = ['pkexec', 'dpkg', '-i', file_path]
    elif file_path.endswith('.rpm') and 'system' in adapters:
        cmd = ['pkexec', 'rpm', '-i', file_path]
    elif file_path.endswith('.pkg.tar.zst') or file_path.endswith('.pkg.tar.xz'):
        cmd = ['pkexec', 'pacman', '-U', '--noconfirm', file_path]
    elif file_path.endswith('.flatpakref') or file_path.endswith('.flatpak'):
        if 'flatpak' in adapters:
            cmd = adapters['flatpak'].install_local(file_path)
        else:
            cmd = ['pkexec', 'flatpak', 'install', '-y', file_path]
    elif file_path.endswith('.AppImage'):
        name = os.path.splitext(os.path.basename(file_path))[0]
        cmd = ['pkexec', 'bash', '-c',
               f'cp "{file_path}" /usr/bin/{name} && '
               f'chmod +x /usr/bin/{name}']
    else:
        print(_c('red', f"  Unknown file type: {file_path}"), file=sys.stderr)
        return False

    print(f"  {_c('cyan', 'Installing from file:')} {_c('bold', file_path)}")
    return _run_cmd(cmd)


def cmd_remove(packages):
    """Remove/uninstall one or more packages.

    Accepts either:
      - A single string (legacy): "firefox"
      - A list of (name, source) tuples: [("firefox", None), ("vlc", "sys")]

    Resolution order per package (mirrors cmd_install):
    1. If *source* is specified, remove from that source.
    2. If name has a prefix (e.g. flatpak:org.gimp.GIMP), remove from that source.
    3. Try each adapter — check if any variation of the name is installed.
    4. Fall back to system adapter with the raw name.
    5. Report failure if not found.

    Returns True if at least one package was removed successfully.
    """
    if isinstance(packages, str):
        packages = [(packages, None)]

    if not packages:
        print(f"  Usage: {_c('bold', f'{CLI_NAME} remove <package>')}", file=sys.stderr)
        print(f"  Examples:", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} remove firefox')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} remove flatpak:org.gimp.GIMP')}", file=sys.stderr)
        print(f"    {_c('dim', f'{CLI_NAME} remove firefox chromium vlc')}", file=sys.stderr)
        return False

    success = False
    for pkg_name, pkg_source in packages:
        if _remove_single(pkg_name, pkg_source):
            success = True
    return success


def _remove_single(package: str, source: str = None) -> bool:
    """Remove a single package. Returns True on success."""
    if not package:
        return False

    adapters = _get_adapters()

    if source and source in adapters:
        cmd = adapters[source].uninstall(package)
        print(f"  {_c('red', 'Removing')} {_c('bold', package)} {_c('dim', f'from {source}...')}")
        return _run_cmd(cmd)

    if not source:
        src, name = _parse_source(package)
        if src and src in adapters:
            cmd = adapters[src].uninstall(name)
            print(f"  {_c('red', 'Removing')} {_c('bold', name)} {_c('dim', f'from {src}...')}")
            return _run_cmd(cmd)
        package = name

    variations = _generate_search_variations(package)
    for src, adapter in adapters.items():
        try:
            installed = adapter.list_installed()
            for variation in variations:
                if variation in installed:
                    cmd = adapter.uninstall(variation)
                    print(f"  {_c('red', 'Removing')} {_c('bold', variation)} {_c('dim', f'from {src}...')}")
                    return _run_cmd(cmd)
        except Exception:
            pass

    if 'system' in adapters:
        cmd = adapters['system'].uninstall(package)
        print(f"  {_c('red', 'Removing')} {_c('bold', package)} {_c('dim', 'from system...')}")
        return _run_cmd(cmd)

    print(_c('red', f"  Package '{package}' not found."), file=sys.stderr)
    return False


def cmd_update():
    """Update/upgrade all packages from all available sources.
    
    Iterates over each adapter and calls its upgrade_system() method.
    The upgrade command (if any) is printed with the source label and executed.
    """
    adapters = _get_adapters()

    print(_c('bold', '  Updating system packages...'))
    print()

    for source, adapter in adapters.items():
        try:
            cmd = adapter.upgrade_system()
            if cmd:
                label, colored_label = SOURCE_LABELS.get(source, (source, source))
                print(f"  {colored_label}")
                _run_cmd(cmd)
        except Exception:
            pass

    return True


def cmd_fix():
    """Fix broken package dependencies.
    
    Detects the system package manager and runs the appropriate fix command:
    - pacman: refresh DBs + remove orphan packages
    - apt-get: apt-get install -f
    - dnf: dnf distro-sync
    - yum: yum distro-sync
    
    Returns True if the fix command succeeded, False otherwise.
    """
    adapters = _get_adapters()
    system = adapters.get('system')

    if shutil.which('pacman'):
        print(f"  {_c('cyan', 'Fixing broken dependencies (pacman)...')}")
        print()
        # First refresh databases, then check for orphans
        _run_cmd(['pkexec', 'pacman', '-Sy'])
        # Remove orphan packages
        print(f"  {_c('dim', 'Removing orphan packages...')}")
        return _run_cmd(['pkexec', 'sh', '-c', 'pacman -Qtdq | xargs -r pacman -Rns --noconfirm'])
    elif shutil.which('apt-get'):
        print(f"  {_c('cyan', 'Fixing broken dependencies (apt)...')}")
        print()
        return _run_cmd(['pkexec', 'apt-get', 'install', '-f', '-y'])
    elif shutil.which('dnf'):
        print(f"  {_c('cyan', 'Fixing broken dependencies (dnf)...')}")
        print()
        return _run_cmd(['pkexec', 'dnf', 'distro-sync', '-y'])
    elif shutil.which('yum'):
        print(f"  {_c('cyan', 'Fixing broken dependencies (yum)...')}")
        print()
        return _run_cmd(['pkexec', 'yum', 'distro-sync', '-y'])
    else:
        print(_c('red', '  No supported package manager found for fixing dependencies.'), file=sys.stderr)
        return False


def cmd_info(packages):
    """Show detailed information about one or more packages.

    Accepts either:
      - A single string (legacy): "firefox"
      - A list of (name, source) tuples

    Resolution order per package:
    1. If *source* is specified, query that source directly.
    2. If name has a prefix (e.g. flatpak:org.gimp.GIMP), query that source.
    3. Try each adapter with each name variation.
    4. Report failure if nothing matched.
    """
    if isinstance(packages, str):
        packages = [(packages, None)]

    if not packages:
        print(f"  Usage: {_c('bold', f'{CLI_NAME} info <package>')}", file=sys.stderr)
        print(f"  Example: {_c('dim', f'{CLI_NAME} info firefox')}", file=sys.stderr)
        return False

    success = False
    for pkg_name, pkg_source in packages:
        if _info_single(pkg_name, pkg_source):
            success = True
    return success


def _info_single(package: str, source: str = None) -> bool:
    """Show info for a single package. Returns True on success."""
    if not package:
        return False

    adapters = _get_adapters()

    if source and source in adapters:
        try:
            info = adapters[source].get_package_info(package)
            _print_package_info(info, source)
            return True
        except Exception as e:
            print(_c('red', f"  Error: {e}"), file=sys.stderr)
            return False

    if not source:
        src, name = _parse_source(package)
        if src and src in adapters:
            try:
                info = adapters[src].get_package_info(name)
                _print_package_info(info, src)
                return True
            except Exception as e:
                print(_c('red', f"  Error: {e}"), file=sys.stderr)
                return False
        package = name

    variations = _generate_search_variations(package)
    for src, adapter in adapters.items():
        try:
            for variation in variations:
                info = adapter.get_package_info(variation)
                if info.get('version') and info['version'] != 'N/A':
                    _print_package_info(info, src)
                    return True
        except Exception:
            pass

    print(_c('red', f"  Package '{package}' not found."), file=sys.stderr)
    return False


# ── Command registry ────────────────────────────────────────────────────────

# Maps CLI command names (and aliases) to their handler functions.
# Multiple aliases can point to the same handler for user convenience.
# Commands that take no arguments (update, fix) are wrapped in lambdas to
# match the () -> bool signature of the others.
COMMANDS = {
    'search':    cmd_search,
    'find':      cmd_search,
    'look':      cmd_search,
    'list':      cmd_list,
    'installed': cmd_list,
    'apps':      cmd_list,
    'install':   cmd_install,
    'get':       cmd_install,
    'add':       cmd_install,
    'remove':    cmd_remove,
    'uninstall': cmd_remove,
    'delete':    cmd_remove,
    'purge':     cmd_remove,
    'update':    lambda: cmd_update(),
    'upgrade':   lambda: cmd_update(),
    'fix':       lambda: cmd_fix(),
    'repair':    lambda: cmd_fix(),
    'info':      cmd_info,
    'details':   cmd_info,
    'show':      cmd_info,
}
