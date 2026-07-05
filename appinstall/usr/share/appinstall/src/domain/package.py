from dataclasses import dataclass
from enum import Enum

class PackageSource(Enum):
    APT = "apt"
    DNF = "dnf"
    BREW = "brew"
    APPIMAGE = "appimage"
    PWA = "pwa"
    SYSTEM = "system"

@dataclass
class Package:
    name: str
    description: str = ""
    source: PackageSource = PackageSource.SYSTEM
    version: str = ""
    is_installed: bool = False
