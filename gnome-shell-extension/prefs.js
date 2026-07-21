import Adw from 'gi://Adw';
import Gtk from 'gi://Gtk?version=4.0';

import {ExtensionPreferences, gettext as _} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class AppInstallUninstallPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage({
            title: _('General'),
            icon_name: 'application-exit-symbolic',
        });
        window.add(page);

        const group = new Adw.PreferencesGroup({
            title: _('Configuration'),
            description: _('Path to the AppInstall executable'),
        });
        page.add(group);

        const pathRow = new Adw.EntryRow({
            title: _('AppInstall Path'),
        });
        pathRow.set_text(settings.get_string('appinstall-path'));
        pathRow.connect('changed', () => {
            settings.set_string('appinstall-path', pathRow.get_text());
        });
        group.add(pathRow);

        const infoGroup = new Adw.PreferencesGroup({
            title: _('Information'),
        });
        page.add(infoGroup);

        const infoLabel = new Gtk.Label({
            label: _('Leave empty to search for AppInstall in the system PATH or use start.py relative to the extension.'),
            wrap: true,
            xalign: 0,
        });
        infoLabel.add_css_class('dim-label');
        infoGroup.add(infoLabel);
    }
}
