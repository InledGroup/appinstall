import shutil
from .apt_adapter import AptAdapter
from .dnf_adapter import DnfAdapter
from .pacman_adapter import PacmanAdapter

def get_package_manager():
    # English: Detect package manager by checking binary availability
    # Español: Detectar el gestor de paquetes comprobando la disponibilidad del binario
    if shutil.which('pacman'):
        return PacmanAdapter()
    elif shutil.which('dnf'):
        return DnfAdapter()
    elif shutil.which('yum'):
        return DnfAdapter()
    else:
        return AptAdapter()

