from functools import lru_cache
from pydantic import BaseSettings

class Settings(BaseSettings):
    APP_NAME  : str = ''
    KUBECONFIG: str = '/tmp/kubeconfig'
    GCP_REGION: str = 'us-central1'
    ASSETS_DIR: str = "/opt/dagster/assets"
    FOLDER_ID : str = "1DG7sSV70VI_voa9mfag0AlLUBgeFEGyq"


    

@lru_cache()
def get_settings() -> Settings:
    return Settings()
