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
