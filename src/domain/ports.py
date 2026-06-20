from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from .package import Package

class PackageManager(ABC):
    @abstractmethod
    def search(self, query: str) -> List[Dict[str, str]]:
        pass

    @abstractmethod
    def list_installed(self) -> List[str]:
        pass

    @abstractmethod
    def install(self, package: str) -> List[str]:
        pass

    @abstractmethod
    def install_multiple(self, packages: List[str]) -> List[str]:
        pass

    @abstractmethod
    def install_local(self, file_path: str) -> List[str]:
        pass

    @abstractmethod
    def uninstall(self, package: str) -> List[str]:
        pass

    @abstractmethod
    def update_cache(self) -> List[str]:
        pass

    @abstractmethod
    def clean_cache(self) -> List[str]:
        pass

    @abstractmethod
    def autoremove(self) -> List[str]:
        pass

    @abstractmethod
    def fix_broken(self) -> List[str]:
        pass

    @abstractmethod
    def get_cache_directory(self) -> str:
        pass

    @abstractmethod
    def get_local_file_info(self, file_path: str) -> Dict[str, str]:
        pass

    @abstractmethod
    def get_package_info(self, package_name: str) -> Dict[str, str]:
        pass

    @abstractmethod
    def install_clamav(self) -> List[str]:
        pass

    @abstractmethod
    def upgrade_system(self) -> List[str]:
        # English: Return the system update and upgrade command
        # Español: Devolver el comando para actualizar y mejorar el sistema
        pass

