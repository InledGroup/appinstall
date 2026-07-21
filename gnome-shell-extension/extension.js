import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {Extension, InjectionManager, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as AppMenu from 'resource:///org/gnome/shell/ui/appMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export default class AppInstallUninstallExtension extends Extension {
    enable() {
        this._injectionManager = new InjectionManager();

        const extensionDir = this.path;
        const settings = this.getSettings();

        this._checkFirstRun(settings, extensionDir);

        this._injectionManager.overrideMethod(
            AppMenu.AppMenu.prototype,
            'setApp',
            originalMethod => {
                return function (app) {
                    originalMethod.call(this, app);

                    if (this._appInstallItem) {
                        this._appInstallItem.destroy();
                        this._appInstallItem = null;
                    }
                    if (this._appInstallSep) {
                        this._appInstallSep.destroy();
                        this._appInstallSep = null;
                    }

                    if (!app)
                        return;

                    const appInfo = app.get_app_info?.() ?? app.app_info;
                    if (!appInfo)
                        return;

                    const desktopId = appInfo.get_id();
                    if (!desktopId)
                        return;

                    this._appInstallSep = new PopupMenu.PopupSeparatorMenuItem();
                    this.addMenuItem(this._appInstallSep);

                    this._appInstallItem = new PopupMenu.PopupMenuItem('Uninstall');
                    this._appInstallItem.connect('activate', () => {
                        _launchUninstall(desktopId, settings, extensionDir);
                    });
                    this.addMenuItem(this._appInstallItem);
                };
            }
        );
    }

    disable() {
        this._injectionManager?.clear();
        this._injectionManager = null;
    }

    _checkFirstRun(settings, extensionDir) {
        if (_isAppInstallAvailable(settings, extensionDir))
            return;

        try {
            if (settings.get_boolean('first-run-shown'))
                return;
            settings.set_boolean('first-run-shown', true);
        } catch (e) {
            // Schema may not be available in nested sessions
        }

        _showFirstRunDialog();
    }
}

function _isAppInstallAvailable(settings, extensionDir) {
    const configuredPath = settings.get_string('appinstall-path');
    if (configuredPath && GLib.file_test(configuredPath, GLib.FileTest.EXISTS))
        return true;

    if (GLib.find_program_in_path('appinstall'))
        return true;

    const startPy = GLib.build_filenamev([extensionDir, '..', '..', '..', 'appinstall', 'start.py']);
    if (GLib.file_test(startPy, GLib.FileTest.EXISTS))
        return true;

    return false;
}

function _showFirstRunDialog() {
    console.log('[appinstall-uninstall] Showing first-run dialog');

    const dialog = new ModalDialog.ModalDialog({
        styleClass: 'appinstall-first-run-dialog',
    });

    const contentBox = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style: 'padding: 24px;',
    });

    const heading = new St.Label({
        text: 'AppInstall required',
        style: 'font-size: 18px; font-weight: bold; margin-bottom: 12px;',
    });
    contentBox.add_child(heading);

    const body = new St.Label({
        text: 'This extension requires AppInstall as its uninstall backend.\n\n' +
            'AppInstall supports Flatpak, Snap, AUR, pacman, deb, rpm, AppImage, Homebrew and more.',
        style: 'font-size: 14px;',
        x_expand: true,
    });
    body.clutter_text.set_line_wrap(true);
    contentBox.add_child(body);

    dialog.contentLayout.add_child(contentBox);

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

    dialog.addButton({
        label: _('Close'),
        action: () => dialog.close(),
    });

    dialog.open();
}

function _launchUninstall(desktopId, settings, extensionDir) {
    const appinstallPath = settings.get_string('appinstall-path');

    let argv;
    if (appinstallPath && GLib.file_test(appinstallPath, GLib.FileTest.EXISTS)) {
        argv = appinstallPath.endsWith('.py')
            ? ['python3', appinstallPath, '--uninstall', desktopId]
            : [appinstallPath, '--uninstall', desktopId];
    } else {
        const startPy = GLib.build_filenamev([extensionDir, '..', '..', '..', 'appinstall', 'start.py']);
        if (GLib.file_test(startPy, GLib.FileTest.EXISTS)) {
            argv = ['python3', startPy, '--uninstall', desktopId];
        } else {
            argv = ['appinstall', '--uninstall', desktopId];
        }
    }

    try {
        const proc = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        );

        proc.communicate_utf8_async(null, null, (source, result) => {
            try {
                const [stdout, stderr] = source.communicate_utf8_finish(result);
                const output = (stdout || stderr || '').trim();

                if (source.get_successful()) {
                    Main.notify(`AppInstall: ${output}`);
                } else {
                    Main.notifyError(
                        'Uninstall failed',
                        output || 'Unknown error'
                    );
                }
            } catch (e) {
                logError(e, '[appinstall-uninstall] Error communicating with process');
                Main.notifyError(
                    'Uninstall error',
                    e.message || 'Unknown error'
                );
            }
        });
    } catch (e) {
        logError(e, '[appinstall-uninstall] Failed to spawn process');
        Main.notifyError(
            'AppInstall not found',
            `Could not launch AppInstall (${argv.join(' ')}). Configure the path in extension preferences.`
        );
    }
}
