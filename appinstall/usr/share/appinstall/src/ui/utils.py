import os
from gi.repository import Gtk, Gdk

def load_css():
    css_provider = Gtk.CssProvider()
    
    # CSS moderno integrado para GNOME
    css_data = """
    .main-window {
        background: @window_bg_color;
    }
    
    .header-bar {
        background: @headerbar_bg_color;
        color: @headerbar_fg_color;
    }
    
    .card {
        background: @card_bg_color;
        border-radius: 12px;
        padding: 24px;
        margin: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .title-label {
        font-size: 1.2em;
        font-weight: bold;
        color: @window_fg_color;
    }
    
    .subtitle-label {
        font-size: 0.9em;
        color: @insensitive_fg_color;
    }
    
    .action-button {
        background: @accent_bg_color;
        color: @accent_fg_color;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: bold;
    }
    
    .secondary-button {
        border-radius: 8px;
        padding: 12px 24px;
    }
    
    .destructive-button {
        background: @error_bg_color;
        color: @error_fg_color;
        border-radius: 8px;
    }
    
    .search-entry {
        border-radius: 8px;
        padding: 8px 12px;
    }
    
    .progress-bar {
        border-radius: 4px;
    }
    
    .status-label {
        color: @insensitive_fg_color;
    }
    
    .list-row {
        border-radius: 8px;
        margin: 2px;
    }
    
    .file-chooser-button {
        border: 2px dashed @borders;
        border-radius: 12px;
        padding: 32px;
        background: @view_bg_color;
    }
    
    .file-chooser-button:hover {
        background: @view_hover_bg_color;
        border-color: @accent_bg_color;
    }

    /* Custom App Store CSS styles */
    .store-section-title {
        font-size: 1.4em;
        font-weight: bold;
        margin-top: 16px;
        margin-bottom: 8px;
    }
    
    .store-app-card {
        padding: 10px 14px;
        border-radius: 12px;
        transition: background-color 0.2s;
    }
    
    .store-app-card:hover {
        background-color: rgba(255, 255, 255, 0.05);
    }
    
    .app-card-icon {
        border-radius: 12px;
        border: 1px solid rgba(0, 0, 0, 0.1);
    }
    
    .app-card-title {
        font-weight: 600;
        font-size: 1.05em;
    }
    
    .app-card-subtitle {
        font-size: 0.85em;
        color: @insensitive_fg_color;
    }
    
    .app-card-button {
        background-color: rgba(53, 132, 228, 0.15);
        color: #3584e4;
        font-weight: bold;
        border-radius: 20px;
        padding: 4px 16px;
        border: none;
        box-shadow: none;
        transition: all 0.2s;
    }
    
    .app-card-button:hover {
        background-color: #3584e4;
        color: #ffffff;
    }
    
    .top-free-card {
        background: @card_bg_color;
        border-radius: 16px;
        padding: 16px;
        margin: 6px;
        min-width: 140px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.05);
        border: 1px solid rgba(0,0,0,0.05);
    }
    
    .top-free-rank {
        font-size: 1.8em;
        font-weight: 800;
        color: rgba(53, 132, 228, 0.6);
        margin-bottom: 4px;
    }
    
    .top-free-title {
        font-weight: bold;
        font-size: 0.95em;
        margin-top: 8px;
        margin-bottom: 8px;
    }
    
    /* Make sidebar icons blue like in the App Store design (icons only) */
    .navigation-sidebar row image {
        color: #3584e4;
    }

    .navigation-sidebar row > box > label,
    .navigation-sidebar row label {
        color: @window_fg_color;
    }
    
    .sidebar-search {
        border-radius: 12px;
        margin-bottom: 8px;
    }
    
    .screenshot-image {
        border-radius: 8px;
    }
    
    .screenshot-container {
        border-radius: 8px;
        border: 1px solid rgba(0, 0, 0, 0.1);
        background-color: rgba(0, 0, 0, 0.05);
    }
    
    .meta-column {
        margin-left: 2px;
        margin-right: 2px;
    }

    .meta-pill {
        background-color: @accent_bg_color;
        border-radius: 9999px;
        padding: 4px 12px;
        min-height: 28px;
        min-width: 60px;
        margin: 0;
        color: @accent_fg_color;
        border: none;
    }

    .meta-pill image {
        color: @accent_fg_color;
    }

    .meta-pill-text {
        font-weight: bold;
        font-size: 13px;
        color: @accent_fg_color;
    }

    .meta-column-label {
        font-size: 12px;
        color: @theme_fg_color;
        opacity: 0.7;
        margin-top: 6px;
    }

    .store-app-card:hover {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(0, 0, 0, 0.1);
    }

    .scrolling-text-container {
        background: transparent;
        border: none;
        box-shadow: none;
    }

    .screenshot-nav-btn {
        background-color: rgba(0, 0, 0, 0.6);
        color: white;
        border-radius: 9999px;
        margin: 24px;
        border: none;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        transition: background-color 0.2s, transform 0.2s;
    }

    .screenshot-nav-btn:hover {
        background-color: rgba(0, 0, 0, 0.85);
        transform: scale(1.1);
    }

    .screenshot-nav-btn image {
        color: white;
    }

    .log-view {
        font-family: monospace;
        font-size: 9pt;
    }

    .pkgbuild-view {
        font-family: monospace;
        font-size: 9pt;
    }

    /* =====================================================================
       Fixed Mac App Store look (theme-independent).
       English: hard-coded dark palette so home + details pages look the same
       no matter which system theme is installed.
       Español: paleta oscura fija para que el inicio y los detalles se vean
       igual sin importar el tema del sistema.
       ===================================================================== */
    .main-window {
        background-color: #1e1e20;
        color: #f2f2f7;
    }

    .main-window label {
        color: #f2f2f7;
    }

    .main-window .title-label {
        color: #f2f2f7;
        font-weight: 800;
    }

    .main-window .subtitle-label {
        color: alpha(#f2f2f7, 0.55);
    }

    .main-window headerbar {
        background-color: #26262a;
        color: #f2f2f7;
    }

    .main-window headerbar label,
    .main-window headerbar button {
        color: #f2f2f7;
    }

    .sidebar-container {
        background-color: #26262a;
    }

    /* Sidebar: icon blue, label normal (fixed MAS theme) */
    .sidebar-container label {
        color: #f2f2f7;
        font-weight: 500;
    }

    .sidebar-container image {
        color: #0a84ff;
    }

    .sidebar-container row:selected label,
    .sidebar-container row:selected image {
        color: #ffffff;
    }

    .sidebar-container row:selected {
        background-color: alpha(#0a84ff, 0.22);
    }

    .sidebar-search {
        background-color: alpha(#f2f2f7, 0.08);
        color: #f2f2f7;
    }

    .main-window .card {
        background-color: #2c2c2e;
        color: #f2f2f7;
        border: none;
        box-shadow: none;
    }

    .store-section-title {
        font-size: 1.35em;
        font-weight: 800;
        color: #f2f2f7;
        margin-top: 16px;
        margin-bottom: 8px;
    }

    /* Ranked list rows: number + icon + name + GET pill */    .store-rank-row {        background-color: transparent;        border-radius: 10px;        padding: 20px 12px;        margin-top: 8px;        margin-bottom: 8px;    }

    .store-rank-row:hover {
        background-color: alpha(#f2f2f7, 0.06);
    }

    .store-rank-number {
        font-size: 1.05em;
        font-weight: 700;
        color: alpha(#f2f2f7, 0.6);
        min-width: 22px;
    }

    .store-rank-name {
        font-weight: 600;
        color: #f2f2f7;
    }

    .store-rank-sub {
        font-size: 0.85em;
        color: alpha(#f2f2f7, 0.55);
    }

    .store-rank-sep {
        color: alpha(#f2f2f7, 0.12);
    }

    .app-card-icon {
        border-radius: 10px;
    }

    .app-card-title {
        font-weight: 600;
        color: #f2f2f7;
    }

    .app-card-subtitle {
        color: alpha(#f2f2f7, 0.55);
    }

    /* GET / Obtener pill: solid MAS blue */
    .app-card-button {
        background-color: #0a84ff;
        color: #ffffff;
        font-weight: bold;
        border-radius: 9999px;
        padding: 4px 16px;
        border: none;
        box-shadow: none;
    }

    .app-card-button:hover {
        background-color: #2f97ff;
        color: #ffffff;
    }

    .top-free-card {
        background-color: transparent;
        border: none;
        box-shadow: none;
    }

    .top-free-rank {
        color: alpha(#f2f2f7, 0.6);
    }

    /* Detail page: info pills over thin rules */
    .meta-row-container {
        border-top: 1px solid alpha(#f2f2f7, 0.15);
        border-bottom: 1px solid alpha(#f2f2f7, 0.15);
        padding-top: 12px;
        padding-bottom: 12px;
        margin-top: 8px;
        margin-bottom: 8px;
    }

    /* Detail info pills: neutral like MAS, no blue highlight */
    .meta-pill {
        background-color: alpha(#f2f2f7, 0.10);
        border-radius: 9999px;
        padding: 4px 14px;
        min-height: 28px;
        min-width: 60px;
        color: #f2f2f7;
        border: none;
    }

    .meta-pill image {
        color: #f2f2f7;
    }

    .meta-pill-text {
        font-weight: bold;
        font-size: 13px;
        color: #f2f2f7;
    }

    .meta-column-label {
        font-size: 11px;
        font-weight: 700;
        color: alpha(#f2f2f7, 0.45);
        margin-top: 6px;
    }

    .screenshot-container {
        background-color: alpha(#f2f2f7, 0.05);
        border: 1px solid alpha(#f2f2f7, 0.12);
    }

    .verified-icon {
        color: #0a84ff;
    }
    """
    
    try:
        css_provider.load_from_string(css_data)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    except Exception as e:
        print(f"Error al cargar el CSS: {e}")

def setup_icon_theme():
    try:
        display = Gdk.Display.get_default()
        if not display:
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        else:
            theme = Gtk.IconTheme.get_for_display(display)
            
        local_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        theme.add_search_path(local_dir)
        theme.add_search_path(os.path.join(local_dir, "appinstall/usr/share/pixmaps"))
        theme.add_search_path(os.getcwd())
    except Exception as e:
        print(f"Advertencia al configurar tema de iconos: {e}")
