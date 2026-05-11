from pydantic_settings import BaseSettings, SettingsConfigDict

# коды лиг football-data.org
LEAGUE_CODES = ["PL", "PD", "SA", "BL1", "FL1", "CL", "WC", "EC", "ELC", "DED", "PPL", "BSA"]

# для этих турниров не передаём season при запросе команд (не привязаны к клубному сезону)
SEASONLESS_CODES = {"WC", "EC"}

# числовые ID лиг в football-data.org (для хранения в БД)
LEAGUE_ID_MAP: dict[str, int] = {
    "PL":  2021,  # Premier League
    "PD":  2014,  # La Liga
    "SA":  2019,  # Serie A
    "BL1": 2002,  # Bundesliga
    "FL1": 2015,  # Ligue 1
    "CL":  2001,  # Champions League
    "WC":  2000,  # World Cup
    "EC":  2018,  # Euro
    "ELC": 2016,  # Championship
    "DED": 2003,  # Eredivisie
    "PPL": 2017,  # Primeira Liga
    "BSA": 2013,  # Brasileirão Série A
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    TELEGRAM_TOKEN: str
    FOOTBALL_DATA_KEY: str
    DATABASE_URL: str
    TIMEZONE: str = "Europe/Moscow"
    LOG_LEVEL: str = "INFO"

    PRE_MATCH_MINUTES: int = 20
    POST_MATCH_MINUTES: int = 110
    SYNC_INTERVAL_HOURS: int = 6


settings = Settings()
