"""
CLI entry point for the application installer.

This module is the top-level command-line interface. It parses the user's
argv, resolves command aliases, routes to the correct handler function from
cli_core, and provides helper utilities for:
  - Displaying formatted help text (_show_help)
  - Detecting the type of a .desktop file (PWA, AppImage, Homebrew)
  - Mapping a file on disk back to its owning system package
  - Looking up which package provides a given .desktop ID
  - Uninstalling an application by its .desktop ID
"""

import sys
import os
import subprocess
import shutil
import re
from typing import Optional, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import CLI_NAME
from src.cli_core import (
    COMMANDS, cmd_search, cmd_list, cmd_search_installed, cmd_install,
    cmd_remove, cmd_update, cmd_fix, cmd_info, _c, _parse_source,
    _normalize_source
)
import src.cli_core as cli_core


def _show_help():
    """
    Print a formatted help screen to stdout.

    Uses _c() (a colour helper from cli_core) to apply ANSI styles such as
    bold, dim, cyan, and green so the output is readable and visually
    structured.  The help text covers:
      - Available commands and their argument signatures
      - Command aliases (e.g. "find" → search, "purge" → remove)
      - The smart multi-word search feature (e.g. "wl clipboard" → "wl-clipboard")
      - Supported package sources (system repos, Flatpak, Snap, AUR, local files)
      - Usage examples
    """
    from src.utils.constants import CURRENT_VERSION
    print(f"""
{_c('bold', CLI_NAME)} {_c('dim', f'v{CURRENT_VERSION}')}  {_c('dim', '— Your friendly package manager')}

{_c('bold', ' USAGE')}
    {CLI_NAME} <command> [arguments]

{_c('bold', ' COMMANDS')}
    {_c('cyan', 'search')}  {_c('dim', '<query>')}       Search for packages
    {_c('cyan', 'list')}    {_c('dim', '[query]')}       List installed packages (optional filter)
    {_c('cyan', 'install')} {_c('dim', '<package>')}    Install a package
    {_c('cyan', 'remove')}  {_c('dim', '<package>')}    Remove a package
    {_c('cyan', 'update')}                 Update system packages
    {_c('cyan', 'fix')}                    Fix broken dependencies
    {_c('cyan', 'info')}    {_c('dim', '<package>')}    Show package details

{_c('bold', ' ALIASES')}
    {_c('dim', 'search')}    find, look
    {_c('dim', 'list')}      installed, apps
    {_c('dim', 'install')}   get, add
    {_c('dim', 'remove')}    uninstall, delete, purge
    {_c('dim', 'update')}    upgrade
    {_c('dim', 'fix')}       repair
    {_c('dim', 'info')}      details, show

{_c('bold', ' SMART SEARCH')}
    Multi-word queries are tried automatically:
    {_c('dim', f'{CLI_NAME} search wl clipboard')}   → also searches "wl-clipboard"
    {_c('dim', f'{CLI_NAME} search visual studio')} → also searches "visual-studio"

{_c('bold', ' MULTI-PACKAGE')}
    {_c('dim', f'{CLI_NAME} install pkg1 pkg2 from flathub')}   {_c('dim', '# same source')}
    {_c('dim', f'{CLI_NAME} install p1 from sys and p2 from fpk')} {_c('dim', '# different sources')}
    {_c('dim', f'{CLI_NAME} remove pkg1 pkg2 pkg3')}            {_c('dim', '# remove multiple')}

{_c('bold', ' PACKAGE SOURCES')}
    {_c('dim', 'Auto-detect:')}  {CLI_NAME} install firefox
    {_c('dim', 'Flatpak:')}      {CLI_NAME} install flatpak:org.gimp.GIMP
    {_c('dim', 'Snap:')}         {CLI_NAME} install snap:code
    {_c('dim', 'AUR:')}          {CLI_NAME} install aur:package-name
    {_c('dim', 'Local file:')}   {CLI_NAME} install /path/to/file.deb

{_c('bold', ' EXAMPLES')}
    {_c('green', f'{CLI_NAME} search firefox')}            {_c('dim', '# search in all sources')}
    {_c('green', f'{CLI_NAME} search wl clipboard')}      {_c('dim', '# smart search with variations')}
    {_c('green', f'{CLI_NAME} list')}                      {_c('dim', '# list all installed')}
    {_c('green', f'{CLI_NAME} list firefox')}              {_c('dim', '# search within installed packages')}
    {_c('green', f'{CLI_NAME} install firefox')}           {_c('dim', '# install from system repos')}
    {_c('green', f'{CLI_NAME} install flatpak:gimp')}     {_c('dim', '# install from Flathub')}
    {_c('green', f'{CLI_NAME} install wl clipboard from flathub')} {_c('dim', '# smart multi-word install')}
    {_c('green', f'{CLI_NAME} install gimp vlc from flathub')}     {_c('dim', '# multiple packages, same source')}
    {_c('green', f'{CLI_NAME} install gimp from fpk and vlc from sys')} {_c('dim', '# different sources')}
    {_c('green', f'{CLI_NAME} remove firefox')}            {_c('dim', '# remove a package')}
    {_c('green', f'{CLI_NAME} remove firefox chromium vlc')} {_c('dim', '# remove multiple packages')}
    {_c('green', f'{CLI_NAME} update')}                    {_c('dim', '# update everything')}
    {_c('green', f'{CLI_NAME} fix')}                       {_c('dim', '# fix broken dependencies')}
    {_c('green', f'{CLI_NAME} info firefox')}              {_c('dim', '# show package details')}
""")


def _parse_multi_package_args(args: list) -> list:
    """Parse CLI arguments for multi-package commands (install, remove, info).

    Supports flexible syntax using 'from' and 'and' keywords:
      - Single package:       ["firefox"]  ->  [("firefox", None)]
      - With source prefix:   ["flatpak:org.gimp.GIMP"]  ->  [("org.gimp.GIMP", "flatpak")]
      - From a source:        ["wl", "clipboard", "from", "flathub"]  ->  [("wl-clipboard", "flathub")]
      - Same source, multi:   ["gimp", "vlc", "from", "flathub"]  ->  [("gimp", "flathub"), ("vlc", "flathub")]
      - Different sources:    ["gimp", "from", "fpk", "and", "vlc", "from", "sys"]  ->  [("gimp", "fpk"), ("vlc", "sys")]
      - Mixed:                ["gimp", "from", "fpk", "and", "vlc", "chromium", "from", "sys"]
                              ->  [("gimp", "fpk"), ("vlc", "sys"), ("chromium", "sys")]

    Multi-word package names joined by spaces are concatenated and
    converted to hyphens (e.g. "wl clipboard" -> "wl-clipboard").

    Args:
        args: Raw argv[2:] list of strings.

    Returns:
        List of (package_name, source_or_None) tuples.
        Returns [] if no valid packages were parsed.
    """
    if not args:
        return []

    lower = [a.lower() for a in args]
    has_from = 'from' in lower
    has_and = 'and' in lower

    if has_from or has_and:
        return _parse_blocks(args, lower)
    else:
        return _parse_legacy(args)


def _parse_blocks(args: list, lower: list) -> list:
    """Parse arguments using 'and'-separated blocks with 'from' source specifiers.

    Each token before 'from' is treated as a separate package name.
    For multi-word package names, use hyphens (e.g. 'wl-clipboard').

    Source names are normalized via _normalize_source, so you can write:
      from flathub / from fpk / from flatpak  → flatpak
      from sys / from system / from apt       → system
      from brew / from homebrew               → brew
    """
    result = []
    blocks = []
    current_block = []

    for i, arg in enumerate(args):
        if lower[i] == 'and':
            if current_block:
                blocks.append(current_block)
            current_block = []
        else:
            current_block.append(arg)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        block_lower = [a.lower() for a in block]
        if 'from' in block_lower:
            idx = block_lower.index('from')
            pkg_tokens = block[:idx]
            src = block[idx + 1] if idx + 1 < len(block) else None
            if pkg_tokens:
                if src:
                    src = _normalize_source(src)
                for t in pkg_tokens:
                    result.append((t, src))
        else:
            pkg_name = ' '.join(block).replace(' ', '-')
            if pkg_name:
                result.append((pkg_name, None))

    return result


def _parse_legacy(args: list) -> list:
    """Parse arguments using legacy prefix syntax (flatpak:, snap:, etc.)."""
    result = []
    for arg in args:
        source, name = _parse_source(arg)
        if source:
            source = _normalize_source(source)
        result.append((name, source))
    return result


def _detect_desktop_file_type(desktop_path: str) -> Tuple[bool, bool, bool]:
    """
    Determine the special type of an application from its .desktop file.

    The function reads the .desktop file and inspects key-value pairs to
    classify the app:

    * PWA (Progressive Web App):
        True when the file contains ``X-AppInstall=PWA`` (an annotation
        added by the appinstall tool) **or** the Exec line uses
        ``--app=`` / ``--application-mode=`` (Chromium flags that launch
        a website as a standalone app).

    * AppImage:
        True when the file contains ``X-AppInstall=AppImage``, meaning
        the .desktop entry was created by appinstall to wrap an AppImage
        binary.

    * Homebrew:
        True when the file contains ``X-AppInstall=Homebrew``, indicating
        the app was installed via the Homebrew (Linuxbrew) adapter.

    Returns a 3-tuple of booleans: (is_pwa, is_appimage, is_brew).
    On any I/O error the file is treated as a normal application and
    (False, False, False) is returned.
    """
    try:
        with open(desktop_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        is_pwa = "X-AppInstall=PWA" in content or "--app=" in content or "--application-mode=" in content
        is_appimage = "X-AppInstall=AppImage" in content
        is_brew = "X-AppInstall=Homebrew" in content
        return is_pwa, is_appimage, is_brew
    except Exception:
        return False, False, False


def _owner_package_for_file(filepath: str) -> Optional[str]:
    """
    Ask the native package manager which installed package owns *filepath*.

    The function probes for one of three package managers — pacman (Arch),
    dpkg (Debian/Ubuntu), or rpm (Fedora/RHEL) — and uses whichever is
    available on the system.

    * pacman: ``pacman -Qo <file>`` outputs a line like
      ``/usr/bin/foo is owned by bar 1.2.3``.  The regex captures the
      package name token.  A Spanish-locale fallback regex
      (``está contenido en``) is also tried because pacman can localise
      its output.

    * dpkg: ``dpkg -S <file>`` outputs ``package: /path/to/file``.  The
      text before the colon is the owning package name.

    * rpm: ``rpm -qf <file>`` outputs the full NEVRA string
      (e.g. ``foo-1.2.3-1.x86_64``).  The function extracts just the
      package name by splitting on ``-`` and ``.``.  An output beginning
      with ``not owned`` is treated as "no owner".

    Returns the package name string on success, or None if no owner is
    found or the command fails.
    """
    if shutil.which('pacman'):
        try:
            out = subprocess.check_output(
                ['pacman', '-Qo', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            match = re.search(r'is owned by (\S+)', out)
            if not match:
                match = re.search(r'está contenido en (\S+)', out)
            if match:
                return match.group(1)
        except Exception:
            pass
    elif shutil.which('dpkg'):
        try:
            out = subprocess.check_output(
                ['dpkg', '-S', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            pkg = out.split(':')[0].strip()
            if pkg:
                return pkg
        except Exception:
            pass
    elif shutil.which('rpm'):
        try:
            out = subprocess.check_output(
                ['rpm', '-qf', filepath],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode('utf-8')
            if out.startswith('not owned'):
                return None
            return out.split('-')[0].split('.')[0]
        except Exception:
            pass
    return None


def _find_package_for_desktop(desktop_id: str) -> Optional[Tuple[str, str]]:
    """
    Resolve a .desktop ID (e.g. ``firefox.desktop``) to an installed package.

    Lookup order — the first match wins:

    1. **Flatpak** – Iterate installed Flatpak refs; if any ref matches
       the app-id portion (with or without the ``.desktop`` suffix),
       return ``("flatpak", ref)``.

    2. **Snap** – Same logic as Flatpak but against installed snaps.

    3. **Desktop file on disk** – Look for the ``.desktop`` file in the
       standard XDG data directories (``/usr/share/applications`` and
       ``~/.local/share/applications``).  If found, classify it:
         * AppImage → ``("appimage", app_id)``
         * PWA      → ``("pwa", app_id)``
         * Homebrew → ``("brew", app_id)``
       Otherwise, ask the system package manager which package owns the
       file.  On Arch (pacman), a further check determines whether the
       owning package is a foreign (AUR) package or a official system
       package, returning ``("aur", pkg)`` or ``("system", pkg)``
       respectively.

    Returns a ``(source, package_name)`` tuple, or None if no match is
    found anywhere.
    """
    app_id = desktop_id.replace(".desktop", "") if desktop_id.endswith(".desktop") else desktop_id

    try:
        from src.infrastructure.adapters.flatpak_adapter import FlatpakAdapter
        fp = FlatpakAdapter()
        if fp.is_available():
            for pkg in fp.list_installed():
                if pkg == app_id or pkg == desktop_id:
                    return ("flatpak", pkg)
    except Exception:
        pass

    try:
        from src.infrastructure.adapters.snap_adapter import SnapAdapter
        sn = SnapAdapter()
        if sn.is_available():
            for pkg in sn.list_installed():
                if pkg == app_id or pkg == desktop_id:
                    return ("snap", pkg)
    except Exception:
        pass

    desktop_dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]

    for desktop_dir in desktop_dirs:
        target = os.path.join(desktop_dir, f"{app_id}.desktop")
        if os.path.exists(target):
            is_pwa, is_appimage, is_brew = _detect_desktop_file_type(target)
            if is_appimage:
                return ("appimage", app_id)
            if is_pwa:
                return ("pwa", app_id)
            if is_brew:
                return ("brew", app_id)

            pkg = _owner_package_for_file(target)
            if pkg:
                if shutil.which('pacman'):
                    try:
                        foreign = subprocess.check_output(
                            ['pacman', '-Qm'], stderr=subprocess.DEVNULL, timeout=5
                        ).decode('utf-8')
                        foreign_pkgs = {line.split()[0] for line in foreign.split('\n') if line.strip()}
                        if pkg in foreign_pkgs:
                            return ("aur", pkg)
                    except Exception:
                        pass
                return ("system", pkg)

    return None


def uninstall_by_desktop_id(desktop_id: str) -> Tuple[bool, str]:
    """
    Uninstall the application identified by a .desktop ID.

    High-level flow:
      1. Call _find_package_for_desktop to determine the source type and
         package name.
      2. If nothing is found, return an error message.
      3. Obtain the correct package-manager instance via the factory and
         build an UninstallService.
      4. Ask UninstallService for the concrete uninstall command, passing
         boolean flags for the source type (appimage, brew, pwa, flatpak,
         snap, aur) so it can choose the right invocation.
      5. Run the command with a 120-second timeout.
      6. Return (True, success_message) on exit code 0, or
         (False, error_message) on failure / timeout.

    Returns a (success: bool, message: str) tuple.
    """
    result = _find_package_for_desktop(desktop_id)
    if not result:
        return False, f"No package found for '{desktop_id}'"

    source, package_name = result

    try:
        from src.infrastructure.adapters.factory import get_package_manager
        from src.application.uninstall_service import UninstallService

        pm = get_package_manager()
        svc = UninstallService(pm)

        cmd = svc.get_uninstall_command(
            package_name,
            is_appimage=(source == "appimage"),
            is_brew=(source == "brew"),
            is_pwa=(source == "pwa"),
            brew_path=shutil.which('brew'),
            is_flatpak=(source == "flatpak"),
            is_snap=(source == "snap"),
            is_aur=(source == "aur")
        )

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            return True, f"'{package_name}' uninstalled successfully"
        else:
            stderr = proc.stderr.strip()
            return False, f"Failed to uninstall '{package_name}': {stderr}"

    except subprocess.TimeoutExpired:
        return False, "Uninstall timed out"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def handle_cli_args(argv: list) -> bool:
    """
    Main CLI argument router.

    Parses ``argv`` and dispatches to the appropriate handler.  Returns
    ``True`` when an error occurred (to set the process exit code) and
    ``False`` when the command completed normally (or was simply a
    help/version display).

    Routing logic, evaluated in order:

    1. **No arguments** (``len(argv) < 2``) → show help, return False.
    2. **Help flags** (``-h``, ``--help``, ``help``) → show help.
    3. **Version flags** (``--version``, ``-V``, ``version``) → print the
       version string and return.
    4. **``--uninstall <desktop-id>``** → treat the next argument as a
       .desktop ID and delegate to uninstall_by_desktop_id.  A missing
       ``.desktop`` suffix is appended automatically.  Returns the
       inverse of the success flag so the caller can set the exit code.
    5. **Known command** (looked up in the COMMANDS dict from cli_core) →
       the remaining argv slice is interpreted per command type:
         * search/find/look — remaining tokens are joined into a single
           query string; missing query prints a usage hint.
         * list/installed/apps — if extra arguments are provided they act
           as a filter (cmd_search_installed); otherwise a full list is
           shown.
         * install/remove/info (and their aliases) — exactly one
           argument is required; missing argument prints a usage hint.
         * Any other registered command — called with no arguments.
    6. **Unknown command** → prints an error and a hint to run help.

    Return value semantics:
      False = success / normal exit (exit code 0)
      True  = error / usage problem (exit code 1)
    """
    if 'parseable' in argv:
        cli_core.PARSEABLE = True
        argv = [a for a in argv if a != 'parseable']

    if len(argv) < 2:
        _show_help()
        return False

    if argv[1] in ('-h', '--help', 'help'):
        _show_help()
        return False

    if argv[1] in ('--version', '-V', 'version'):
        from src.utils.constants import CURRENT_VERSION
        print(f"{CLI_NAME} v{CURRENT_VERSION}")
        return False

    if argv[1] == '--uninstall':
        if len(argv) < 3:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} --uninstall <desktop-id>')}", file=sys.stderr)
            return True
        desktop_id = argv[2]
        if not desktop_id.endswith(".desktop"):
            desktop_id += ".desktop"
        success, message = uninstall_by_desktop_id(desktop_id)
        print(f"  {message}")
        return not success

    command = argv[1].lower()
    args = argv[2:] if len(argv) > 2 else []

    if command not in COMMANDS:
        print(_c('red', f"  Unknown command: '{command}'"), file=sys.stderr)
        print(_c('dim', f"  Run '{CLI_NAME} help' for usage."), file=sys.stderr)
        return True

    func = COMMANDS[command]

    if command in ('search', 'find', 'look'):
        query = ' '.join(args) if args else ''
        if not query:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} {command} <query>')}", file=sys.stderr)
            return True
        return not func(query)
    elif command in ('list', 'installed', 'apps'):
        if args:
            query = ' '.join(args)
            return not cmd_search_installed(query)
        return not func()
    elif command in ('install', 'get', 'add',
                     'remove', 'uninstall', 'delete', 'purge',
                     'info', 'details', 'show'):
        if not args:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} {command} <argument>')}", file=sys.stderr)
            return True
        packages = _parse_multi_package_args(args)
        if not packages:
            print(f"  Usage: {_c('bold', f'{CLI_NAME} {command} <package> [from <source>]')}", file=sys.stderr)
            return True
        return not func(packages)
    else:
        return not func()
