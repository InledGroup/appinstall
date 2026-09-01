import os
import re
import hashlib
import threading
from gi.repository import Gtk, Adw, GLib, Gdk
from src.infrastructure.services.localization import _

def get_deterministic_reviews(app_id, app_name):
    # Deterministic rating between 4.1 and 4.9
    h = int(hashlib.md5(app_id.encode('utf-8')).hexdigest(), 16)
    rating = 4.0 + (h % 10) / 10.0
    if rating > 5.0: rating = 5.0
    elif rating < 3.5: rating = 4.2
    
    # Review templates in Spanish
    comments = [
        ("Jaime G.", 5, "Excelente rendimiento y diseño. Esencial en mi día a día."),
        ("María S.", 4, "Funciona muy bien en Linux. Muy estable y recomendada."),
        ("Carlos R.", 5, "Instalación limpia y rápida. Sin problemas."),
        ("Ana M.", 4, "Muy buena aplicación, cumple perfectamente con su función."),
        ("Lucas B.", 5, "De las mejores aplicaciones que he probado últimamente. Imprescindible."),
        ("Laura T.", 4, "Interfaz limpia y muy intuitiva. Me encanta.")
    ]
    
    # Select 3 reviews deterministically
    reviews = []
    num_comments = len(comments)
    for idx in range(3):
        comment_idx = (h + idx) % num_comments
        reviewer, stars, text = comments[comment_idx]
        reviews.append({
            'author': reviewer,
            'rating': stars,
            'text': text
        })
        
    # Number of ratings: e.g. from 120 to 9500
    ratings_count = 100 + (h % 9400)
    
    return rating, ratings_count, reviews


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    # Replace list items with bullets
    text = re.sub(r'<li>\s*', '• ', raw_html)
    # Replace paragraphs and line breaks
    text = re.sub(r'</p>|<br\s*/?>', '\n\n', text)
    # Strip all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode XML/HTML entities
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
    # Clean up double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

class PackageDetailsWidget(Gtk.Box):
    def __init__(self, parent_window, info, on_install_callback, on_uninstall_callback, back_callback):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.parent_window = parent_window
        self.on_install_callback = on_install_callback
        self.on_uninstall_callback = on_uninstall_callback
        self.back_callback = back_callback
        self.cached_screenshots = info.get('cached_screenshots', [])
        self.add_css_class("main-window")
        
        # Scrolled window directly as content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)
        self.append(scrolled)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        scrolled.set_child(main_box)
        
        # Simple chevron-left back button at the top
        top_navigation_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        back_btn = Gtk.Button()
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.add_css_class("flat")
        back_btn.add_css_class("circular")
        back_btn.connect("clicked", lambda b: self.back_callback())
        top_navigation_box.append(back_btn)
        main_box.append(top_navigation_box)        # 1. Header Card (Icon + Title + Version + Developer on Left, Button on Right)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        header_box.set_hexpand(True)
        
        info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        info_box.set_hexpand(True)
        header_box.append(info_box)
        
        # Icon (supports local files, cached icons, and symbolic names)
        icon_path = info.get('icon', '')
        if icon_path and os.path.exists(icon_path):
            icon_image = Gtk.Image.new_from_file(icon_path)
        elif icon_path and icon_path.startswith('http'):
            try:
                from src.utils.system import get_cached_icon
                cached = get_cached_icon(icon_path, info.get('name', 'app'))
                if cached and os.path.exists(cached):
                    icon_image = Gtk.Image.new_from_file(cached)
                else:
                    icon_image = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
            except Exception:
                icon_image = Gtk.Image.new_from_icon_name("system-software-install-symbolic")
        else:
            icon_name = icon_path if icon_path else "system-software-install-symbolic"
            icon_image = Gtk.Image.new_from_icon_name(icon_name)
        
        icon_image.set_pixel_size(96)
        icon_image.set_halign(Gtk.Align.START)
        icon_image.set_valign(Gtk.Align.CENTER)
        info_box.append(icon_image)
        
        # Text block
        text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        text_vbox.set_valign(Gtk.Align.CENTER)
        info_box.append(text_vbox)
        
        title_label = Gtk.Label(label=info.get('name', ''), xalign=0)
        title_label.add_css_class("title-label")
        title_label.set_wrap(True)
        title_label.set_max_width_chars(30)
        text_vbox.append(title_label)
        
        version_label = Gtk.Label(label=info.get('version', ''), xalign=0)
        version_label.add_css_class("subtitle-label")
        text_vbox.append(version_label)
        
        developer = info.get('developer', '')
        if developer:
            dev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            dev_box.set_halign(Gtk.Align.START)
            
            dev_label = Gtk.Label(label=developer, xalign=0)
            dev_label.add_css_class("subtitle-label")
            dev_box.append(dev_label)
            
            if info.get('verified'):
                verified_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
                verified_icon.set_tooltip_text(_("Autor verificado"))
                verified_icon.add_css_class("verified-icon")
                dev_box.append(verified_icon)
                
            text_vbox.append(dev_box)
            
        # Button box (Right-aligned)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        btn_box.set_valign(Gtk.Align.CENTER)
        
        self.is_installed = info.get('is_installed', False)
        if self.is_installed:
            self.install_btn = Gtk.Button(label=_("Desinstalar"))
            self.install_btn.add_css_class("destructive-action")
            self.install_btn.connect("clicked", self.on_uninstall_clicked)
        else:
            self.install_btn = Gtk.Button(label=_("Instalar"))
            self.install_btn.add_css_class("suggested-action")
            self.install_btn.connect("clicked", self.on_install_clicked)
            
        self.install_btn.add_css_class("app-card-button")
        btn_box.append(self.install_btn)
        header_box.append(btn_box)
        
        main_box.append(header_box)

        # Hashing and Rating calculations
        rating, ratings_count, reviews_list = get_deterministic_reviews(info.get('app_id', info.get('name', '')), info.get('name', ''))

        # 1.5 Metadata Row Container (homogeneous layout spanning full width with no scroll)
        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        meta_row.add_css_class("meta-row-container")
        meta_row.set_hexpand(True)
        meta_row.set_homogeneous(True)
        meta_row.set_halign(Gtk.Align.FILL)
        
        def add_meta_col(pill_content, label_text):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.add_css_class("meta-column")
            col.set_valign(Gtk.Align.START)
            col.set_halign(Gtk.Align.CENTER)
            
            # Pill content box
            pill_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            pill_box.set_halign(Gtk.Align.CENTER)
            pill_box.set_valign(Gtk.Align.CENTER)
            
            if isinstance(pill_content, Gtk.Widget):
                pill_box.append(pill_content)
            elif isinstance(pill_content, str):
                lbl = Gtk.Label(label=pill_content)
                lbl.add_css_class("meta-pill-text")
                pill_box.append(lbl)
                
            # Use Gtk.Frame as the meta-pill to guarantee background rendering
            pill = Gtk.Frame()
            pill.add_css_class("meta-pill")
            pill.set_child(pill_box)
            pill.set_halign(Gtk.Align.CENTER)
            pill.set_valign(Gtk.Align.CENTER)
            
            col.append(pill)
            
            label_sub = Gtk.Label(label=label_text)
            label_sub.add_css_class("meta-column-label")
            label_sub.set_wrap(True)
            label_sub.set_justify(Gtk.Justification.CENTER)
            col.append(label_sub)
            
            meta_row.append(col)
            
        source = info.get('source', '')
        size_val = info.get('size', '')
        
        # 2. Formato (Siempre visible)
        source_format = source.upper() if source else _("NATIVO")
        img_format = Gtk.Image.new_from_icon_name("package-x-generic-symbolic")
        img_format.set_pixel_size(20)
        img_format.set_halign(Gtk.Align.CENTER)
        img_format.set_valign(Gtk.Align.CENTER)
        add_meta_col(img_format, source_format)
        
        # 3. Tamaño (Solo si está disponible y no es N/A)
        if size_val and size_val != 'N/A':
            add_meta_col(size_val, _("Descarga"))
            
        # 4. Desarrollador (Solo si está disponible y no es N/A)
        dev_name = info.get('developer', '')
        if dev_name and dev_name != 'N/A':
            if len(dev_name) > 15:
                dev_name = dev_name[:15] + "..."
            add_meta_col(dev_name, _("Desarrollador"))
            
        # 5. Verificado (Solo si es verdadero)
        if info.get('verified'):
            img_ver = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
            img_ver.set_pixel_size(20)
            img_ver.set_halign(Gtk.Align.CENTER)
            img_ver.set_valign(Gtk.Align.CENTER)
            add_meta_col(img_ver, _("Verificado"))
            
        # Añadir el contenedor directamente a main_box
        if meta_row.get_first_child():
            main_box.append(meta_row)

        # 2. Screenshots Section (Now placed directly under the header and metadata row)
        cached_screenshots = info.get('cached_screenshots', [])
        if cached_screenshots:
            screenshots_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            screenshots_card.add_css_class("card")
            
            screenshots_title = Gtk.Label(label=_("Capturas de pantalla"), xalign=0)
            screenshots_title.add_css_class("title-label")
            screenshots_card.append(screenshots_title)
            
            scrolled_shots = Gtk.ScrolledWindow()
            scrolled_shots.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scrolled_shots.set_min_content_height(200)
            
            shots_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            scrolled_shots.set_child(shots_hbox)
            
            for path in cached_screenshots:
                if os.path.exists(path):
                    img = Gtk.Picture.new_for_filename(path)
                    img.set_content_fit(Gtk.ContentFit.CONTAIN)
                    img.set_size_request(320, 180)
                    img.add_css_class("screenshot-image")
                    
                    # Make screenshot expandable on click
                    click_gesture = Gtk.GestureClick()
                    click_gesture.connect("released", lambda gesture, n_press, x, y, p=path: self.on_screenshot_clicked(p))
                    img.add_controller(click_gesture)
                    
                    img_box = Gtk.Box()
                    img_box.add_css_class("screenshot-container")
                    img_box.append(img)
                    shots_hbox.append(img_box)
                    
            screenshots_card.append(scrolled_shots)
            main_box.append(screenshots_card)

        # 3. Description Card
        desc_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        desc_section.add_css_class("card")
        
        desc_title = Gtk.Label(label=_("Información"), xalign=0)
        desc_title.add_css_class("title-label")
        desc_section.append(desc_title)
        
        desc_text = Gtk.Label(label=clean_html(info.get('description', '')), xalign=0)
        desc_text.set_wrap(True)
        desc_text.set_max_width_chars(60)
        desc_section.append(desc_text)
        
        main_box.append(desc_section)

        # 3.5 README Section (for Pulsar Store packages)
        readme_url = info.get('readme_url', '')
        if readme_url and info.get('source') == 'pulsar':
            readme_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            readme_card.add_css_class("card")
            
            readme_title = Gtk.Label(label=_("README"), xalign=0)
            readme_title.add_css_class("title-label")
            readme_card.append(readme_title)
            
            readme_scroll = Gtk.ScrolledWindow()
            readme_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            readme_scroll.set_min_content_height(200)
            readme_scroll.set_max_content_height(400)
            
            readme_view = Gtk.TextView()
            readme_view.set_editable(False)
            readme_view.set_cursor_visible(False)
            readme_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            readme_view.add_css_class("readme-view")
            readme_view.get_buffer().set_text(_("Cargando README..."))
            readme_scroll.set_child(readme_view)
            readme_card.append(readme_scroll)
            
            main_box.append(readme_card)
            
            # Fetch README in background thread
            def _fetch_readme():
                try:
                    import requests
                    r = requests.get(readme_url, timeout=10)
                    if r.status_code == 200:
                        md = r.text
                        # Simple markdown to text conversion
                        import re
                        text = md
                        # Remove code blocks
                        text = re.sub(r'```[\s\S]*?```', '', text)
                        # Remove inline code
                        text = re.sub(r'`([^`]+)`', r'\1', text)
                        # Remove images
                        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
                        # Convert links to text
                        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
                        # Remove headings markers
                        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
                        # Remove bold/italic
                        text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
                        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
                        text = re.sub(r'\*([^*]+)\*', r'\1', text)
                        # Convert tables to simple format
                        text = re.sub(r'\|([^\n]+)\|', lambda m: ' | '.join(c.strip() for c in m.group(1).split('|') if c.strip()), text)
                        text = re.sub(r'^[-:|\s]+$', '', text, flags=re.MULTILINE)
                        # Remove horizontal rules
                        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
                        # Clean up
                        text = re.sub(r'\n{3,}', '\n\n', text)
                        text = text.strip()
                        GLib.idle_add(readme_view.get_buffer().set_text, text)
                except Exception as e:
                    GLib.idle_add(readme_view.get_buffer().set_text, f"Error loading README: {e}")
            
            threading.Thread(target=_fetch_readme, daemon=True).start()

        # 4. Technical Details Card
        details_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        details_card.add_css_class("card")
        
        details_title = Gtk.Label(label=_("Detalles técnicos"), xalign=0)
        details_title.add_css_class("title-label")
        details_card.append(details_title)
        
        details_grid = Gtk.Grid()
        details_grid.set_column_spacing(24)
        details_grid.set_row_spacing(10)
        
        # Package size
        details_grid.attach(Gtk.Label(label=_("Tamaño instalado"), xalign=1), 0, 0, 1, 1)
        details_grid.attach(Gtk.Label(label=info.get('size', 'N/A'), xalign=0), 1, 0, 1, 1)
        
        # Package format
        ext = "N/A"
        if 'ext' in info: ext = info['ext']
        if info.get('source') in ['flatpak', 'snap', 'aur', 'brew']:
            ext = info['source']
        details_grid.attach(Gtk.Label(label=_("Formato"), xalign=1), 0, 1, 1, 1)
        details_grid.attach(Gtk.Label(label=ext.upper(), xalign=0), 1, 1, 1, 1)

        # Dependencies
        deps = info.get('dependencies', [])
        if deps:
            if isinstance(deps, list):
                display_deps = ", ".join(deps[:15])
                if len(deps) > 15:
                    display_deps += f" ... y {len(deps) - 15} más"
            else:
                display_deps = str(deps)
        else:
            display_deps = _("Ninguna")
            
        deps_label = Gtk.Label(label=display_deps, xalign=0)
        deps_label.set_wrap(True)
        deps_label.set_max_width_chars(45)
        
        details_grid.attach(Gtk.Label(label=_("Dependencias"), xalign=1), 0, 2, 1, 1)
        details_grid.attach(deps_label, 1, 2, 1, 1)
        
        details_card.append(details_grid)
        main_box.append(details_card)

        # 5. PKGBUILD Section (only for AUR packages, shown before installing)
        pkgbuild = info.get('pkgbuild', '')
        if info.get('source') == 'aur' and pkgbuild:
            pkgbuild_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            pkgbuild_card.add_css_class("card")
            
            pkgbuild_title = Gtk.Label(label=_("PKGBUILD"), xalign=0)
            pkgbuild_title.add_css_class("title-label")
            pkgbuild_card.append(pkgbuild_title)
            
            pkgbuild_warn = Gtk.Label(label=_("Este paquete se compila desde el AUR. Revisa el PKGBUILD antes de instalarlo: cualquier archivo se ejecuta con tus permisos."), xalign=0)
            pkgbuild_warn.add_css_class("subtitle-label")
            pkgbuild_warn.set_wrap(True)
            pkgbuild_card.append(pkgbuild_warn)
            
            pkgbuild_scroll = Gtk.ScrolledWindow()
            pkgbuild_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            pkgbuild_scroll.set_min_content_height(200)
            pkgbuild_scroll.set_max_content_height(300)
            
            pkgbuild_view = Gtk.TextView()
            pkgbuild_view.set_editable(False)
            pkgbuild_view.set_cursor_visible(False)
            pkgbuild_view.set_wrap_mode(Gtk.WrapMode.NONE)
            pkgbuild_view.add_css_class("pkgbuild-view")
            pkgbuild_view.get_buffer().set_text(pkgbuild)
            pkgbuild_scroll.set_child(pkgbuild_view)
            pkgbuild_card.append(pkgbuild_scroll)
            
            main_box.append(pkgbuild_card)

    def on_install_clicked(self, button):
        self.on_install_callback()

    def on_uninstall_clicked(self, button):
        self.on_uninstall_callback()

    def on_screenshot_clicked(self, path):
        if not self.cached_screenshots:
            return
            
        try:
            current_index = self.cached_screenshots.index(path)
        except ValueError:
            current_index = 0
            
        dialog = Gtk.Window(transient_for=self.get_root(), modal=True)
        dialog.set_title(_("Captura de pantalla"))
        dialog.set_default_size(960, 540)
        dialog.add_css_class("screenshot-viewer-window")
        
        # We will use an overlay
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        
        # Image widget
        img = Gtk.Picture()
        img.set_content_fit(Gtk.ContentFit.CONTAIN)
        img.set_hexpand(True)
        img.set_vexpand(True)
        overlay.set_child(img)
        
        def update_image(index):
            nonlocal current_index
            current_index = index
            # Check bounds
            if current_index < 0:
                current_index = len(self.cached_screenshots) - 1
            elif current_index >= len(self.cached_screenshots):
                current_index = 0
                
            img.set_filename(self.cached_screenshots[current_index])
            
        update_image(current_index)
        
        # Navigation buttons overlay
        # Left button
        prev_btn = Gtk.Button()
        prev_btn.set_icon_name("go-previous-symbolic")
        prev_btn.add_css_class("screenshot-nav-btn")
        prev_btn.add_css_class("screenshot-nav-left")
        prev_btn.set_size_request(48, 48)
        prev_btn.set_halign(Gtk.Align.START)
        prev_btn.set_valign(Gtk.Align.CENTER)
        prev_btn.connect("clicked", lambda b: update_image(current_index - 1))
        overlay.add_overlay(prev_btn)
        
        # Right button
        next_btn = Gtk.Button()
        next_btn.set_icon_name("go-next-symbolic")
        next_btn.add_css_class("screenshot-nav-btn")
        next_btn.add_css_class("screenshot-nav-right")
        next_btn.set_size_request(48, 48)
        next_btn.set_halign(Gtk.Align.END)
        next_btn.set_valign(Gtk.Align.CENTER)
        next_btn.connect("clicked", lambda b: update_image(current_index + 1))
        overlay.add_overlay(next_btn)
        
        dialog.set_child(overlay)
        dialog.present()
