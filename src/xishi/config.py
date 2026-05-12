from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    yibu_api_key: str = ""

    # 把 base_url 也放 Settings——不写死在代码里，未来切自建网关只改 .env
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
    deepseek_base_url: str = "https://api.deepseek.com"

    database_url: str = "postgresql://localhost:5432/xishi"

    @property
    def llm_configured(self) -> bool:
        return bool(self.moonshot_api_key or self.deepseek_api_key)


settings = Settings()
