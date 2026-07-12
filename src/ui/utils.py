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
    
    /* Make sidebar icons blue like in the App Store design */
    .navigation-sidebar row image {
        color: #3584e4;
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
        overflow: hidden;
        background-color: rgba(0, 0, 0, 0.05);
    }
    
    .meta-col-card {
        min-width: 110px;
        min-height: 70px;
        margin-left: 4px;
        margin-right: 4px;
        padding: 8px 12px;
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
