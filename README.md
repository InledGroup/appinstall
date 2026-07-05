![Banner AppInstall](/corp/AppInstall%20banner.png)
# AppInstall  
It's Clean my Mac, but for Linux distros.  
Compatible with Debian, Fedora and Arch Linux based distros.  

## Features.  
- Uninstall visually ANY package of your system  
- Install Appimages, .deb, .rpm, .pkg.tar.zst and PWAs
- Install and search apps from APT, DNF and Homebrew
- Free disk space.  
- Scan for viruses  
- Fix installation errors.  
- Install ANY package visually, whether from the distro repositories or from any package.
> [!NOTE]
> Support for AUR, Flathub and Snap will be added soon

> With Appinstall, you won't need technical knowledge to do the most basic things in Linux: managing applications.  

## Installation  
Download the latest version of Appinstall and double-click on the .deb or .rpm file to install it.  (Only if you're using GNOME or KDE, in other cases you'll need to use the terminal).

### Arch Linux
Las dependencias se resuelven e instalan automáticamente al instalar el paquete `.pkg.tar.zst`. 

Si necesitas instalarlas manualmente, puedes ejecutar:
```bash
sudo pacman -Syu python python-gobject gtk4 libadwaita python-requests python-packaging polkit
```
