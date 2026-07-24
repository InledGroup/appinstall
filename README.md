![Banner AppInstall](/corp/AppInstall%20banner.png)

> [!NOTE]
> Keep Appinstall updated, set up the [Inled Repo](https://apt.inled.es)

# AppInstall  
It's Clean my Mac, but for Linux distros.  
Compatible with Debian, Fedora and Arch Linux based distros.   
A new abstraction layer for distro package managers.

## Features.  
- Uninstall visually ANY package of your system  
- Install Appimages, .deb, .rpm, .pkg.tar.zst and PWAs
- Install and search apps from APT, DNF and Homebrew
- Free disk space.  
- Scan for viruses  
- Fix installation errors.  
- Install ANY package visually, whether from the distro repositories or from any package.
- **App Store look**

## GUI  
You can open AppInstall normally and set it as default application for installation files.  

## CLI (PKM)  
Now Appinstall comes with a brand new CLI interface. A new abstraction layer for package managers. The same commands for APT, DNF, Homebrew, PACMAN, AUR, FLATHUB, SNAP...  
No strange syntax, all with words that can be dictated. There are no scripts or other elements, just words.
You can type `pkm help` in your terminal to see how to use it. Even if you get the wrong command, there is compatibility with synonyms.

## Installation  
Download the latest version of Appinstall and double-click on the .deb or .rpm file to install it.  (Only if you're using GNOME or KDE, in other cases you'll need to use the terminal).

### Arch Linux
Las dependencias se resuelven e instalan automáticamente al instalar el paquete `.pkg.tar.zst`. 

Si necesitas instalarlas manualmente, puedes ejecutar:
```bash
sudo pacman -Syu python python-gobject gtk4 libadwaita python-requests python-packaging polkit
```
---
v21