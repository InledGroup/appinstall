/**
 * Appinstall Uninstall on Context Menu of GNOME
 *
 * In this GUADEC, the one in 2026 (which was in my city), I heard that they were trying to implement
 * the uninstall button in the context menu of an app when right-clicking on its icon in GNOME. 
 * I searched but I couldn't find where they were doing it, so it thinked that since 
 * I had already created an app that acted as an abstraction layer, I could do it and that's it.
 * 
 * I used translator to translate the complex comments from spanish to english (i dont have a high level on english languaje) 
 * Also, i write this comments because is more easy to me to read the code and i have serious memory problems.
 * I used AI to write some comments. Seems a lot of code, but is very tiny.
 * 
 * 
 * What it does:
 * Adds an "Uninstall" option to the app context menu in the GNOME Shell
 * app grid. Delegates the actual uninstall to the AppInstall CLI tool
 * (appi) which handles Flatpak, Snap, AUR, pacman, deb, rpm, AppImage,
 * and Homebrew packages.
 *
 * Architecture:
 *   1. On enable(), we monkey-patch AppMenu.AppMenu.prototype.setApp
 *      to inject a separator + "Uninstall" menu item every time GNOME
 *      Shell sets an app on the context menu.
 *   2. When the user clicks "Uninstall", we spawn the AppInstall CLI
 *      with --uninstall <desktop-id> and show the result as a GNOME
 *      notification (toast).
 *   3. On first run (if AppInstall is not found), we show a modal
 *      dialog explaining the requirement and linking to the GitHub repo.
 */

// ── Imports ────────────────────────────────────────────────────────────────

// Gio: GIO library — used for Subprocess, SubprocessFlags, and
//      AppInfo.launch_default_for_uri (opening URLs in the default browser).
import Gio from 'gi://Gio';

// GLib: Core GLib library — used for file_test (checking file existence),
//       find_program_in_path (finding executables on PATH), and
//       build_filenamev (constructing file paths).
import GLib from 'gi://GLib';

// St: GNOME Shell Toolkit (Clutter-based widgets) — used for BoxLayout
//     and Label widgets in the first-run modal dialog.
import St from 'gi://St';

// Extension: Base class for GNOME Shell extensions (ESM module, GNOME 45+).
// InjectionManager: Safe monkey-patching utility that tracks overrides
//                   and restores originals on disable().
// gettext (_): Localization helper (used for button labels).
import {Extension, InjectionManager, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

// AppMenu: Shell UI module providing AppMenu.prototype.setApp, which is
//          called by GNOME Shell whenever the user right-clicks an app
//          in the app grid. We patch this to inject our menu item.
import * as AppMenu from 'resource:///org/gnome/shell/ui/appMenu.js';

// Main: Shell UI module providing Main.notify (info toast) and
//       Main.notifyError (error toast with title + body).
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// ModalDialog: Shell UI module for creating modal dialogs with buttons.
//              Used for the first-run "AppInstall required" dialog.
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';

// PopupMenu: Shell UI module providing PopupMenuItem (clickable menu entry)
//            and PopupSeparatorMenuItem (visual divider between items).
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';


// ── Extension class ────────────────────────────────────────────────────────

export default class AppInstallUninstallExtension extends Extension {

    /**
     * enable() is called when the extension is loaded or GNOME Shell starts.
     * It sets up the monkey-patch on AppMenu to inject the Uninstall item.
     */
    enable() {
        // InjectionManager tracks all overrides so they can be cleanly
        // reversed in disable(). This prevents leaks and conflicts with
        // other extensions.
        this._injectionManager = new InjectionManager();

        // extensionDir is the on-disk path to this extension's files.
        // settings is the GSettings object for our schema (appinstall-path,
        // first-run-shown).
        const extensionDir = this.path;
        const settings = this.getSettings();

        // Check if AppInstall CLI is available (appi) :). If not, show the first-run
        // dialog (only once, tracked via GSettings).
        this._checkFirstRun(settings, extensionDir);

        // Override AppMenu.AppMenu.prototype.setApp — this method is called
        // by GNOME Shell every time the user right-clicks an app icon in
        // the app grid or app menu. We inject our Uninstall item after
        // the original method runs. 
        this._injectionManager.overrideMethod(
            AppMenu.AppMenu.prototype,
            'setApp',
            originalMethod => {
                return function (app) {
                    // Call the original setApp first — this populates the
                    // menu with the app's normal items (Open, Show Details, etc.)
                    originalMethod.call(this, app);

                    // Clean up any previously injected items. setApp is called
                    // each time a new app is selected, so we must destroy the
                    // old items to avoid duplicates. (Extension rules...)
                    if (this._appInstallItem) {
                        this._appInstallItem.destroy();
                        this._appInstallItem = null;
                    }
                    if (this._appInstallSep) {
                        this._appInstallSep.destroy();
                        this._appInstallSep = null;
                    }

                    // Guard: if no app is set (e.g., menu is being cleared),
                    // don't add anything.
                    if (!app)
                        return;

                    // Get the AppInfo object from the app. In GNOME 50+,
                    // app.get_app_info() may return undefined, so we also
                    // try app.app_info as a fallback. We love fallbacks :)
                    const appInfo = app.get_app_info?.() ?? app.app_info;
                    if (!appInfo)
                        return;

                    // The desktop ID is the unique identifier for the app
                    // (e.g., "org.mozilla.firefox.desktop"). This is what
                    // we pass to the AppInstall CLI for uninstallation.
                    const desktopId = appInfo.get_id();
                    if (!desktopId)
                        return;

                    // Add a visual separator before our item.
                    this._appInstallSep = new PopupMenu.PopupSeparatorMenuItem();
                    this.addMenuItem(this._appInstallSep);

                    // Add the "Uninstall" menu item. When clicked, it
                    // triggers _launchUninstall which spawns the CLI.
                    this._appInstallItem = new PopupMenu.PopupMenuItem('Uninstall');
                    this._appInstallItem.connect('activate', () => {
                        _launchUninstall(desktopId, settings, extensionDir);
                    });
                    this.addMenuItem(this._appInstallItem);
                };
            }
        );
    }

    /**
     * disable() is called when the extension is unloaded or GNOME Shell exits.
     * It restores the original setApp method and cleans up.
     */
    disable() {
        // InjectionManager.clear() restores all overridden methods to their
        // original implementations. This is critical for clean extension
        // unloading without side effects on the shell.
        this._injectionManager?.clear();
        this._injectionManager = null;
    }

    /**
     * _checkFirstRun — Shows the first-run dialog if AppInstall CLI is
     * not found on the system. The dialog is shown only once (tracked
     * via the 'first-run-shown' GSettings key).
     */
    _checkFirstRun(settings, extensionDir) {
        // If the CLI is already available, no need to show anything.
        if (_isAppInstallAvailable(settings, extensionDir))
            return;

        // Check if we've already shown the dialog. The try/catch handles
        // the case where the GSettings schema is not compiled (e.g., in
        // a nested Mutter DevKit session during development).
        try {
            if (settings.get_boolean('first-run-shown'))
                return;
            settings.set_boolean('first-run-shown', true);
        } catch (e) {
            // Schema may not be available in nested sessions, anyway, proceed.
        }

        _showFirstRunDialog();
    }
}


// ── Helper: Check if AppInstall CLI is available ───────────────────────────

/**
 * _isAppInstallAvailable — Probes for the AppInstall CLI using a four-step
 * resolution order:
 *
 *   1. User-configured path from extension preferences (appinstall-path).
 *   2. 'appi' found on the system PATH (new CLI name).
 *   3. 'appinstall' found on the system PATH (legacy name).
 *   4. start.py relative to the extension directory (development layout).
 *
 * Returns true on the first match, false if none found.
 */
function _isAppInstallAvailable(settings, extensionDir) {
    // Step 1: Check the user-configured path in extension preferences.
    const configuredPath = settings.get_string('appinstall-path');
    if (configuredPath && GLib.file_test(configuredPath, GLib.FileTest.EXISTS))
        return true;

    // Step 2: Check if 'appi' is on PATH (new name)
    if (GLib.find_program_in_path('appi'))
        return true;

    // Step 3: Check if the legacy 'appinstall' command is on PATH.
    if (GLib.find_program_in_path('appinstall'))
        return true;

    // Step 4: Development layout — look for start.py relative to the
    // extension directory (../../appinstall/start.py).
    const startPy = GLib.build_filenamev([extensionDir, '..', '..', '..', 'appinstall', 'start.py']);
    if (GLib.file_test(startPy, GLib.FileTest.EXISTS))
        return true;

    return false;
}


// ── Helper: First-run modal dialog ─────────────────────────────────────────

/**
 * _showFirstRunDialog — Displays a modal dialog informing the user that
 * AppInstall is required as the uninstall backend. Uses pure GJS widgets
 * (ModalDialog, St.BoxLayout, St.Label) — so we comply with GJS Extension rules.
 *
 * The dialog has two buttons:
 *   - "Install AppInstall" → opens the GitHub repo in the default browser.
 *   - "Close" → dismisses the dialog.
 */
function _showFirstRunDialog() {
    console.log('[appinstall-uninstall] Showing first-run dialog');

    // Create a modal dialog with a custom CSS class for styling.
    const dialog = new ModalDialog.ModalDialog({
        styleClass: 'appinstall-first-run-dialog',
    });

    // Build the content layout as a vertical box with padding.
    const contentBox = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style: 'padding: 24px;',
    });

    // Bold heading label.
    const heading = new St.Label({
        text: 'AppInstall required',
        style: 'font-size: 18px; font-weight: bold; margin-bottom: 12px;',
    });
    contentBox.add_child(heading);

    // Body text with line wrapping enabled.
    const body = new St.Label({
        text: 'This extension requires AppInstall as its uninstall backend.\n\n' +
            'AppInstall supports Flatpak, Snap, AUR, pacman, deb, rpm, AppImage, Homebrew and more.',
        style: 'font-size: 14px;',
        x_expand: true,
    });
    body.clutter_text.set_line_wrap(true);
    contentBox.add_child(body);

    // Add the content box to the dialog's content layout.
    dialog.contentLayout.add_child(contentBox);

    // "Install AppInstall" button — launches the GitHub repo URL in the
    // user's default browser via GIO's AppInfo API.
    dialog.addButton({
        label: _('Install AppInstall'),
        action: () => {
            Gio.AppInfo.launch_default_for_uri(
                'https://github.com/InledGroup/appinstall',
                null
            );
            dialog.close();
        },
    });

    // "Close" button — simply dismisses the dialog.
    dialog.addButton({
        label: _('Close'),
        action: () => dialog.close(),
    });

    // Open the dialog modally (blocks input to the rest of the shell).
    dialog.open();
}


// ── Helper: Launch uninstall subprocess ────────────────────────────────────

/**
 * _launchUninstall — Resolves the AppInstall CLI path and spawns it with
 * --uninstall <desktop-id>. Shows the result as a GNOME notification.
 *
 * CLI resolution order (same as _isAppInstallAvailable):
 *   1. User-configured path from extension preferences.
 *   2. 'appi' on PATH.
 *   3. 'appinstall' on PATH.
 *   4. start.py relative to the extension directory.
 *   5. Fallback to 'appi' (will fail gracefully with an error notification).
 *
 * If the configured path ends in '.py', it is prefixed with 'python3'.
 *
 * The subprocess is spawned asynchronously using GIO's Subprocess API.
 * stdout and stderr are captured and displayed as notifications:
 *   - Success → Main.notify (info toast).
 *   - Failure → Main.notifyError (error toast with title + body).
 */
function _launchUninstall(desktopId, settings, extensionDir) {
    // Read the user-configured path from extension preferences.
    const appinstallPath = settings.get_string('appinstall-path');

    // Build the argv array for the subprocess. We try multiple paths
    // in priority order to find the CLI.
    let argv;
    if (appinstallPath && GLib.file_test(appinstallPath, GLib.FileTest.EXISTS)) {
        // Step 1: User-configured path. If it's a Python script,
        // prefix with python3 so it can be executed directly.
        argv = appinstallPath.endsWith('.py')
            ? ['python3', appinstallPath, '--uninstall', desktopId]
            : [appinstallPath, '--uninstall', desktopId];
    } else {
        // Step 2: Check if 'appi' is on PATH (new CLI name).
        const appiPath = GLib.find_program_in_path('appi');
        if (appiPath) {
            argv = [appiPath, '--uninstall', desktopId];
        } else {
            // Step 3: Check if the legacy 'appinstall' is on PATH.
            const appinstallPath2 = GLib.find_program_in_path('appinstall');
            if (appinstallPath2) {
                argv = [appinstallPath2, '--uninstall', desktopId];
            } else {
                // Step 4: Development layout — look for start.py
                // relative to the extension directory.
                const startPy = GLib.build_filenamev([extensionDir, '..', '..', '..', 'appinstall', 'start.py']);
                if (GLib.file_test(startPy, GLib.FileTest.EXISTS)) {
                    argv = ['python3', startPy, '--uninstall', desktopId];
                } else {
                    // Step 5: Last resort — try 'appi' directly.
                    // This will fail if not installed, triggering
                    // the error notification below.
                    argv = ['appi', '--uninstall', desktopId];
                }
            }
        }
    }

    try {
        // Spawn the subprocess with stdout and stderr piped so we
        // can capture the output for the notification.
        const proc = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        );

        // Communicate asynchronously — this doesn't block the shell.
        // When the process finishes, the callback fires with the output.
        proc.communicate_utf8_async(null, null, (source, result) => {
            try {
                const [stdout, stderr] = source.communicate_utf8_finish(result);
                const output = (stdout || stderr || '').trim();

                if (source.get_successful()) {
                    // Success: show an info toast with the CLI output.
                    Main.notify(`AppInstall: ${output}`);
                } else {
                    // Non-zero exit code: show an error toast.
                    Main.notifyError(
                        'Uninstall failed',
                        output || 'Unknown error'
                    );
                }
            } catch (e) {
                // Error reading the process output (e.g., process crashed).
                logError(e, '[appinstall-uninstall] Error communicating with process');
                Main.notifyError(
                    'Uninstall error',
                    e.message || 'Unknown error'
                );
            }
        });
    } catch (e) {
        // Failed to spawn the process at all (e.g., CLI not found,
        // permission denied). Show a helpful error suggesting the
        // user configure the path in extension preferences.
        logError(e, '[appinstall-uninstall] Failed to spawn process');
        Main.notifyError(
            'AppInstall not found',
            `Could not launch AppInstall (${argv.join(' ')}). Configure the path in extension preferences.`
        );
    }
}
