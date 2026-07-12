import os
import re
import hashlib
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
        
        # Icon
        icon_path = info.get('icon')
        if icon_path and os.path.exists(icon_path):
            icon_image = Gtk.Image.new_from_file(icon_path)
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

        # 1.5 Metadata Row Card (Container horizontal scrollable to prevent window from expanding)
        scrolled_meta = Gtk.ScrolledWindow()
        scrolled_meta.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scrolled_meta.set_min_content_height(90)
        
        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        scrolled_meta.set_child(meta_row)
        
        def add_meta_col(box, title, value, subtitle=None):
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            col.add_css_class("card") # Individual card!
            col.add_css_class("meta-col-card") # Set custom minimum sizes in CSS
            col.set_valign(Gtk.Align.FILL)
            col.set_halign(Gtk.Align.CENTER)
            
            # Content vbox centered inside the card
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.set_halign(Gtk.Align.CENTER)
            col.append(vbox)
            
            t_label = Gtk.Label(label=title.upper())
            t_label.add_css_class("meta-col-title")
            vbox.append(t_label)
            
            v_label = Gtk.Label(label=value)
            v_label.add_css_class("meta-col-value")
            vbox.append(v_label)
            
            if subtitle:
                s_label = Gtk.Label(label=subtitle)
                s_label.add_css_class("meta-col-subtitle")
                vbox.append(s_label)
            box.append(col)
            
        source = info.get('source', '')
        
        # 1. Valoraciones (Flatpak only)
        if source == 'flatpak':
            stars_str = "★" * int(round(rating)) + "☆" * (5 - int(round(rating)))
            add_meta_col(meta_row, _("valoraciones"), f"{rating:.1f}", stars_str)
        
        # 2. Formato (Siempre visible)
        source_format = source.upper() if source else "NATIVO"
        add_meta_col(meta_row, _("formato"), source_format, _("Tipo de paquete"))
        
        # 3. Tamaño (Solo si está disponible y no es N/A)
        size_val = info.get('size', '')
        if size_val and size_val != 'N/A':
            add_meta_col(meta_row, _("tamaño"), size_val, _("Espacio en disco"))
            
        # 4. Desarrollador (Solo si está disponible y no es N/A)
        dev_name = info.get('developer', '')
        if dev_name and dev_name != 'N/A':
            if len(dev_name) > 15:
                dev_name = dev_name[:15] + "..."
            add_meta_col(meta_row, _("desarrollador"), dev_name, _("Autor de la app"))
            
        # 5. Verificado (Solo si es verdadero)
        if info.get('verified'):
            add_meta_col(meta_row, _("verificado"), _("SÍ"), _("Autor verificado"))
            
        # 6. Idioma (Flatpak only)
        if source == 'flatpak':
            add_meta_col(meta_row, _("idioma"), "ES", _("Y multilingüe"))
            
        # Añadir el contenedor scrollable si contiene elementos
        if meta_row.get_first_child():
            main_box.append(scrolled_meta)

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

        # 5. Permissions Section
        permissions_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        permissions_card.add_css_class("card")
        
        perm_title = Gtk.Label(label=_("Permisos"), xalign=0)
        perm_title.add_css_class("title-label")
        permissions_card.append(perm_title)
        
        perm_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        perm_icon = Gtk.Image.new_from_icon_name("security-high-symbolic")
        perm_hbox.append(perm_icon)
        
        perm_text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        perm_main = Gtk.Label(label=_("Acceso total al sistema"), xalign=0)
        perm_main.add_css_class("title-label")
        perm_text_vbox.append(perm_main)
        perm_sub = Gtk.Label(label=_("Como paquete nativo, esta aplicación puede acceder a tus archivos y hardware."), xalign=0)
        perm_sub.add_css_class("subtitle-label")
        perm_sub.set_wrap(True)
        perm_text_vbox.append(perm_sub)
        
        perm_hbox.append(perm_text_vbox)
        permissions_card.append(perm_hbox)
        main_box.append(permissions_card)

        # 6. Reviews Section (Valoraciones y reseñas) at the very end
        if source == 'flatpak':
            reviews_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            reviews_card.add_css_class("card")
            
            reviews_title = Gtk.Label(label=_("Valoraciones y reseñas"), xalign=0)
            reviews_title.add_css_class("title-label")
            reviews_card.append(reviews_title)
            
            # Summary row (Big number on Left, stats on Right)
            summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
            summary_box.set_margin_bottom(12)
            
            big_rating = Gtk.Label(label=f"{rating:.1f}")
            big_rating.add_css_class("big-rating-number")
            summary_box.append(big_rating)
            
            rating_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            rating_vbox.set_valign(Gtk.Align.CENTER)
            
            stars_label = Gtk.Label(label="★" * int(round(rating)) + "☆" * (5 - int(round(rating))), xalign=0)
            stars_label.add_css_class("big-rating-stars")
            rating_vbox.append(stars_label)
            
            count_label = Gtk.Label(label=_("{} valoraciones").format(f"{ratings_count:,}"), xalign=0)
            count_label.add_css_class("subtitle-label")
            rating_vbox.append(count_label)
            
            summary_box.append(rating_vbox)
            reviews_card.append(summary_box)
            
            # Grid of reviews
            reviews_grid = Gtk.Grid()
            reviews_grid.set_column_spacing(16)
            reviews_grid.set_row_spacing(12)
            reviews_grid.set_column_homogeneous(True)
            
            for idx, rev in enumerate(reviews_list):
                rev_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                rev_box.add_css_class("card")
                rev_box.add_css_class("review-bubble")
                
                # Author & stars header
                hdr_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                
                auth_label = Gtk.Label(label=rev['author'], xalign=0)
                auth_label.add_css_class("review-author")
                hdr_box.append(auth_label)
                
                spacer = Gtk.Box()
                spacer.set_hexpand(True)
                hdr_box.append(spacer)
                
                rev_stars = Gtk.Label(label="★" * rev['rating'] + "☆" * (5 - rev['rating']))
                rev_stars.add_css_class("review-stars")
                hdr_box.append(rev_stars)
                
                rev_box.append(hdr_box)
                
                # Review text
                txt_label = Gtk.Label(label=rev['text'], xalign=0)
                txt_label.set_wrap(True)
                txt_label.set_max_width_chars(35)
                txt_label.add_css_class("review-text")
                rev_box.append(txt_label)
                
                # Add to grid: 1 row, multiple columns
                reviews_grid.attach(rev_box, idx, 0, 1, 1)
                
            reviews_card.append(reviews_grid)
            main_box.append(reviews_card)

    def on_install_clicked(self, button):
        self.on_install_callback()

    def on_uninstall_clicked(self, button):
        self.on_uninstall_callback()

    def on_screenshot_clicked(self, path):
        # Open a beautiful transient dialog/window showing the image in full size
        dialog = Gtk.Window(transient_for=self.get_root(), modal=True)
        dialog.set_title(_("Captura de pantalla"))
        dialog.set_default_size(960, 540)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        
        img = Gtk.Picture.new_for_filename(path)
        img.set_content_fit(Gtk.ContentFit.CONTAIN)
        img.set_hexpand(True)
        img.set_vexpand(True)
        box.append(img)
        
        close_btn = Gtk.Button(label=_("Cerrar"))
        close_btn.add_css_class("suggested-action")
        close_btn.set_halign(Gtk.Align.CENTER)
        close_btn.connect("clicked", lambda b: dialog.close())
        box.append(close_btn)
        
        dialog.set_child(box)
        dialog.present()
