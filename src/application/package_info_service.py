import os
import subprocess
import tempfile
import re
from typing import Dict
from src.domain.ports import PackageManager

class PackageInfoService:
    def __init__(self, package_manager: PackageManager):
        self.package_manager = package_manager

    def get_info(self, file_path: str) -> Dict[str, str]:
        if not file_path or not os.path.exists(file_path):
            return {}

        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.deb' or ext == '.rpm':
            return self.package_manager.get_local_file_info(file_path)
        elif ext == '.appimage':
            return self._get_appimage_info(file_path)
        
        return {}

    def _get_appimage_info(self, file_path: str) -> Dict[str, str]:
        info = {
            'name': os.path.basename(file_path).replace('.AppImage', '').replace('.appimage', ''),
            'version': 'N/A',
            'description': 'Aplicación en formato AppImage',
            'size': f"{os.path.getsize(file_path) / (1024*1024):.1f} MB",
            'icon': ''
        }
        
        try:
            # Try to extract icon and desktop file
            temp_dir = tempfile.mkdtemp(prefix='appimage_info_')
            # Use --appimage-extract to get metadata files if possible
            # But let's be careful, some AppImages might not support it or be too large
            # Alternative: use 'unsquashfs' if available or just look for the icon
            
            # For now, let's try a quick extraction of common metadata files
            icon_output = os.path.join(temp_dir, 'icon.png')
            
            # Try to get .DirIcon
            try:
                # We can't easily extract just one file without running it or using squashfs-tools
                # If squashfs-tools is available, it's better
                if subprocess.run(['which', 'unsquashfs'], capture_output=True).returncode == 0:
                    subprocess.run(['unsquashfs', '-d', temp_dir, '-f', '-n', '-i', file_path, '.DirIcon'], 
                                   capture_output=True, timeout=5)
                    extracted_icon = os.path.join(temp_dir, '.DirIcon')
                    if os.path.exists(extracted_icon):
                        import shutil
                        final_icon = os.path.join(tempfile.gettempdir(), 'appinstall_icons', f"{info['name']}.png")
                        os.makedirs(os.path.dirname(final_icon), exist_ok=True)
                        shutil.copy(extracted_icon, final_icon)
                        info['icon'] = final_icon
                    
                    # Try to find a desktop file for better name/description
                    subprocess.run(['unsquashfs', '-d', temp_dir, '-f', '-n', '-i', file_path, '*.desktop'], 
                                   capture_output=True, timeout=5)
                    for f in os.listdir(temp_dir):
                        if f.endswith('.desktop'):
                            with open(os.path.join(temp_dir, f), 'r') as df:
                                content = df.read()
                                name_match = re.search(r'^Name=(.*)$', content, re.MULTILINE)
                                if name_match: info['name'] = name_match.group(1).strip()
                                desc_match = re.search(r'^Comment=(.*)$', content, re.MULTILINE)
                                if desc_match: info['description'] = desc_match.group(1).strip()
                                break
            except:
                pass
                
            # Clean up temp dir
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass
            
        return info
