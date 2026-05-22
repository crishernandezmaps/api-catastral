from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "127.0.0.1"
    db_port: int = 5435
    db_name: str = "catastro"
    db_user: str = "catastro_app"
    db_password: str
    db_pool_min: int = 5
    db_pool_max: int = 20
    api_key: str = ""  # si está vacío, no requiere autenticación

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
