from pydantic_settings import BaseSettings
from dotenv import find_dotenv, load_dotenv

# Load .env file
load_dotenv(find_dotenv())

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    ODOO_URL: str
    ODOO_DB: str
    ODOO_USERNAME: str
    ODOO_PASSWORD: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
