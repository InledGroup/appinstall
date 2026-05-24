import shutil
from .apt_adapter import AptAdapter
from .dnf_adapter import DnfAdapter

def get_package_manager():
    if shutil.which('dnf'):
        return DnfAdapter()
    elif shutil.which('yum'):
        return DnfAdapter()
    else:
        return AptAdapter()
