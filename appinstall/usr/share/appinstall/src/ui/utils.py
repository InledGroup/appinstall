import os
from gi.repository import Gtk, Gdk

def load_css():
    css_provider = Gtk.CssProvider()
    
    # CSS adaptativo moderno para GNOME / Libadwaita (Soporte perfecto Modo Claro y Oscuro)
    css_data = """
    .main-window {
        background-color: @window_bg_color;
        color: @window_fg_color;
    }
    
    .header-bar {
        background-color: transparent;
        border-bottom: 1px solid alpha(currentColor, 0.08);
    }
    
    .card {
        background-color: @card_bg_color;
        color: @card_fg_color;
        border-radius: 12px;
        padding: 18px;
        margin: 6px;
        border: 1px solid alpha(currentColor, 0.08);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
    }
    
    .title-label {
        font-size: 1.15em;
        font-weight: 700;
        color: @window_fg_color;
    }
    
    .subtitle-label {
        font-size: 0.9em;
        color: alpha(currentColor, 0.6);
    }
    
    .action-button {
        background-color: #0a84ff;
        color: #ffffff;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        border: none;
    }

    .action-button:hover {
        background-color: #0071e3;
    }
    
    .secondary-button {
        background-color: alpha(currentColor, 0.08);
        color: @window_fg_color;
        border-radius: 8px;
        padding: 10px 20px;
        border: 1px solid alpha(currentColor, 0.1);
    }

    .secondary-button:hover {
        background-color: alpha(currentColor, 0.14);
    }
    
    .destructive-button {
        background-color: @error_bg_color;
        color: @error_fg_color;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
    }
    
    .search-entry {
        border-radius: 10px;
        padding: 6px 10px;
    }
    
    .progress-bar {
        border-radius: 4px;
    }
    
    .status-label {
        color: alpha(currentColor, 0.65);
    }
    
    .list-row {
        border-radius: 8px;
        margin: 2px;
    }
    
    .file-chooser-button {
        border: 2px dashed alpha(currentColor, 0.2);
        border-radius: 12px;
        padding: 24px;
        background-color: alpha(currentColor, 0.03);
    }
    
    .file-chooser-button:hover {
        background-color: alpha(currentColor, 0.06);
        border-color: #0a84ff;
    }

    /* Estilos App Store / Pulsar Store */
    .store-section-title {
        font-size: 1.3em;
        font-weight: 700;
        color: @window_fg_color;
        margin-top: 16px;
        margin-bottom: 8px;
    }
    
    .store-app-card {
        padding: 12px 14px;
        border-radius: 12px;
        transition: background-color 0.2s;
    }
    
    .store-app-card:hover {
        background-color: alpha(currentColor, 0.06);
    }
    
    .app-card-icon {
        border-radius: 12px;
        border: none;
        background: transparent;
    }
    
    .app-card-title {
        font-weight: 600;
        font-size: 1.05em;
        color: @window_fg_color;
    }
    
    .app-card-subtitle {
        font-size: 0.85em;
        color: alpha(currentColor, 0.6);
    }
    
    .app-card-button {
        background-color: #0a84ff;
        color: #ffffff;
        font-weight: 700;
        font-size: 13px;
        border-radius: 9999px;
        padding: 5px 16px;
        border: none;
        box-shadow: none;
    }
    
    .app-card-button:hover {
        background-color: #0071e3;
        color: #ffffff;
    }

    .app-card-button-secondary {
        background-color: alpha(currentColor, 0.08);
        color: @window_fg_color;
        font-weight: 600;
        font-size: 13px;
        border-radius: 9999px;
        padding: 5px 16px;
        border: none;
    }

    .app-card-button-secondary:hover {
        background-color: alpha(currentColor, 0.15);
    }
    
    .top-free-card {
        background-color: @card_bg_color;
        color: @card_fg_color;
        border-radius: 14px;
        padding: 14px;
        margin: 4px;
        min-width: 140px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        border: 1px solid alpha(currentColor, 0.08);
    }
    
    .top-free-rank {
        font-size: 1.6em;
        font-weight: 800;
        color: alpha(#0a84ff, 0.7);
        margin-bottom: 4px;
    }
    
    .top-free-title {
        font-weight: 600;
        font-size: 0.95em;
        color: @window_fg_color;
        margin-top: 6px;
        margin-bottom: 6px;
    }
    
    .store-rank-row {
        background-color: transparent;
        border-radius: 10px;
        padding: 12px 10px;
        margin-top: 4px;
        margin-bottom: 4px;
    }

    .store-rank-row:hover {
        background-color: alpha(currentColor, 0.06);
    }

    .store-rank-number {
        font-size: 1.05em;
        font-weight: 700;
        color: alpha(currentColor, 0.45);
        min-width: 24px;
    }

    .store-rank-name {
        font-weight: 600;
        color: @window_fg_color;
    }

    .store-rank-sub {
        font-size: 0.85em;
        color: alpha(currentColor, 0.6);
    }
    
    /* Barra lateral */
    .sidebar-container {
        background-color: alpha(currentColor, 0.025);
        border-right: 1px solid alpha(currentColor, 0.08);
    }

    .sidebar-container label {
        color: @window_fg_color;
        font-weight: 500;
    }

    .sidebar-container image {
        color: #0a84ff;
    }

    .sidebar-container row {
        border-radius: 8px;
        margin-bottom: 3px;
        padding: 4px 6px;
        transition: background-color 0.15s;
    }

    .sidebar-container row:selected {
        background-color: alpha(#0a84ff, 0.16);
    }

    .sidebar-container row:selected label {
        color: #0a84ff;
        font-weight: 600;
    }

    .sidebar-container row:selected image {
        color: #0a84ff;
    }
    
    .sidebar-search {
        border-radius: 10px;
        margin-bottom: 8px;
        background-color: alpha(currentColor, 0.05);
    }
    
    .screenshot-image {
        border-radius: 8px;
        border: none;
    }
    
    .screenshot-container {
        border-radius: 8px;
        border: none;
        background-color: transparent;
    }

    .bottom-status-bar {
        background-color: @card_bg_color;
        border-top: 1px solid alpha(currentColor, 0.08);
        padding: 6px 14px 10px 14px;
    }

    .status-title-label {
        font-weight: 700;
        font-size: 0.95em;
        color: @window_fg_color;
        margin-right: 8px;
    }

    .status-log-label {
        font-family: monospace;
        font-size: 0.85em;
        color: alpha(currentColor, 0.65);
    }

    .bottom-progress-bar {
        min-height: 4px;
        border-radius: 4px;
        margin-top: 4px;
    }
    
    .meta-row-container {
        border-top: 1px solid alpha(currentColor, 0.08);
        border-bottom: 1px solid alpha(currentColor, 0.08);
        padding-top: 12px;
        padding-bottom: 12px;
        margin-top: 8px;
        margin-bottom: 8px;
    }

    .meta-column {
        margin-left: 6px;
        margin-right: 6px;
    }

    .meta-value-box {
        min-height: 28px;
    }

    .meta-value-text {
        font-weight: 800;
        font-size: 1.25em;
        color: @window_fg_color;
    }

    .meta-value-box image {
        color: @window_fg_color;
    }

    .meta-column-label {
        font-size: 11px;
        font-weight: 600;
        color: alpha(currentColor, 0.55);
        margin-top: 2px;
        text-transform: uppercase;
        letter-spacing: 0.03em;
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

    .log-view, .pkgbuild-view {
        font-family: monospace;
        font-size: 9pt;
    }

    .verified-icon {
        color: #0a84ff;
    }

    .badge {
        padding: 3px 8px;
        border-radius: 8px;
        font-size: 10px;
        font-weight: 700;
    }
    
    .badge-system {
        background-color: rgba(53, 132, 228, 0.15);
        color: #3584e4;
    }
    
    .badge-flatpak {
        background-color: rgba(143, 80, 157, 0.15);
        color: #8f509d;
    }
    
    .badge-snap {
        background-color: rgba(224, 27, 36, 0.15);
        color: #e01b24;
    }
    
    .badge-aur {
        background-color: rgba(18, 140, 204, 0.15);
        color: #128ccc;
    }
    
    .badge-brew {
        background-color: rgba(246, 178, 107, 0.15);
        color: #f6b26b;
    }
    
    .badge-pulsar {
        background-color: rgba(10, 132, 255, 0.15);
        color: #0a84ff;
    }

    .badge-success {
        background-color: rgba(46, 194, 126, 0.18);
        color: #2ec27e;
    }

    .badge-warning {
        background-color: rgba(230, 97, 0, 0.18);
        color: #e66100;
    }

    .badge-danger {
        background-color: rgba(224, 27, 36, 0.18);
        color: #e01b24;
    }

    .badge-generic {
        background-color: rgba(120, 120, 120, 0.15);
        color: #787878;
    }

    .compact-tab-btn {
        padding: 4px 14px;
        min-height: 28px;
        font-size: 0.85rem;
        border-radius: 6px;
    }

    .readme-view {
        font-size: 0.95rem;
        line-height: 1.6;
        padding: 14px;
        color: @window_fg_color;
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
