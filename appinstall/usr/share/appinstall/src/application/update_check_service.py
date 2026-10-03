import requests
from packaging import version
from src.utils.constants import CURRENT_VERSION, GITHUB_REPO

class UpdateCheckService:
    def check_for_updates(self):
        """Comprueba las actualizaciones conectando con la API de GitHub."""
        try:
            # Add a user agent to avoid GitHub API rate limiting
            headers = {'User-Agent': f'AppInstall/{CURRENT_VERSION}'}
            
            # Add timeout and better error handling
            response = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", 
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                release_data = response.json()
                latest_version = release_data['tag_name'].lstrip('v')
                release_url = release_data['html_url']
                
                # Comparar versiones
                if version.parse(latest_version) > version.parse(CURRENT_VERSION):
                    return (True, latest_version, release_url)
                return (False, latest_version, release_url)
            elif response.status_code == 403:
                print("Rate limit exceeded or access forbidden. Check GitHub API usage.")
                return None
            else:
                print(f"Error checking for updates: HTTP {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("Timeout while checking for updates")
            return None
        except requests.exceptions.ConnectionError:
            print("Connection error while checking for updates")
            return None
        except Exception as e:
            print(f"Unexpected error checking for updates: {str(e)}")
            return None

    def get_latest_version(self) -> str:
        """Obtiene la última versión disponible de la aplicación."""
        res = self.check_for_updates()
        if res:
            return res[1]
        return None
