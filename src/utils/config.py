"""Configuration management."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    bot_token: str = ""
    chat_id: str = ""


class FiltersConfig(BaseModel):
    """Filtering configuration."""
    min_edge: float = 5.0
    leagues: List[str] = Field(default_factory=lambda: ["all"])
    max_hours_to_kickoff: int = 24


class OddsApiConfig(BaseModel):
    """Odds-API.io specific configuration."""
    api_key: str = ""
    enabled: bool = False
    min_ev_percent: float = 5.0
    max_ev_percent: float = 25.0
    bookmakers: List[str] = Field(default_factory=lambda: [
        "bet365", "danskespil", "unibet_dk", "coolbet"
    ])
    prop_markets_only: bool = True
    refresh_interval_minutes: int = 5


class Settings(BaseModel):
    """Application settings."""
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    sportsbooks: List[str] = Field(default_factory=lambda: [
        "betsson", "leovegas", "unibet", "betway"
    ])
    leagues: List[str] = Field(default_factory=lambda: [
        "england_-_premier_league",
        "spain_-_la_liga",
        "germany_-_bundesliga",
        "italy_-_serie_a",
        "france_-_ligue_1",
    ])
    target_markets: List[str] = Field(default_factory=lambda: [
        "Player Shots", "Player Shots On Target", "Player Fouls", "Player Cards",
        "Player Goals", "Player Assists",
        "Total Shots", "Total Shots On Target", "Total Corners",
        "Asian Handicap", "Asian Handicap Corners"
    ])
    min_edge_percent: float = 5.0
    max_edge_percent: float = 50.0
    min_odds: float = 1.3
    max_odds: float = 15.0
    min_books: int = 2
    refresh_interval_minutes: int = 3
    hours_ahead: int = 24
    filters: FiltersConfig = Field(default_factory=FiltersConfig)

    # Odds-API.io configuration
    oddsapi: OddsApiConfig = Field(default_factory=OddsApiConfig)


class BookmakerInfo(BaseModel):
    """Bookmaker information."""
    name: str
    priority: int = 99
    enabled: bool = True


class BookmakersConfig(BaseModel):
    """Bookmakers configuration."""
    bookmakers: Dict[str, BookmakerInfo] = Field(default_factory=dict)
    default_sportsbooks: List[str] = Field(default_factory=list)


class ConfigManager:
    """Manages application configuration files."""

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize the config manager.

        Args:
            config_dir: Path to config directory. Defaults to ./config
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            # Look for config in current directory or parent
            self.config_dir = Path("config")
            if not self.config_dir.exists():
                self.config_dir = Path(__file__).parent.parent.parent / "config"

        self._settings: Optional[Settings] = None
        self._bookmakers: Optional[BookmakersConfig] = None

    @property
    def settings_path(self) -> Path:
        """Path to settings.json."""
        return self.config_dir / "settings.json"

    @property
    def bookmakers_path(self) -> Path:
        """Path to bookmakers.json."""
        return self.config_dir / "bookmakers.json"

    def load_settings(self) -> Settings:
        """Load settings from file and environment variables."""
        settings_data = {}

        # Load from file if exists
        if self.settings_path.exists():
            with open(self.settings_path, "r") as f:
                settings_data = json.load(f)

        # Override with environment variables
        if os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_CHAT_ID"):
            if "telegram" not in settings_data:
                settings_data["telegram"] = {}
            if os.environ.get("TELEGRAM_BOT_TOKEN"):
                settings_data["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
            if os.environ.get("TELEGRAM_CHAT_ID"):
                settings_data["telegram"]["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

        # Odds-API.io configuration from environment
        if os.environ.get("ODDSAPI_API_KEY"):
            if "oddsapi" not in settings_data:
                settings_data["oddsapi"] = {}
            settings_data["oddsapi"]["api_key"] = os.environ["ODDSAPI_API_KEY"]
            settings_data["oddsapi"]["enabled"] = True

        self._settings = Settings(**settings_data)
        return self._settings

    def save_settings(self, settings: Settings) -> None:
        """Save settings to file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        with open(self.settings_path, "w") as f:
            json.dump(settings.model_dump(), f, indent=2)

        self._settings = settings

    def update_settings(self, updates: Dict[str, Any]) -> Settings:
        """Update specific settings fields."""
        current = self.get_settings()
        current_dict = current.model_dump()

        # Deep merge updates
        self._deep_merge(current_dict, updates)

        new_settings = Settings(**current_dict)
        self.save_settings(new_settings)
        return new_settings

    def _deep_merge(self, base: dict, updates: dict) -> None:
        """Recursively merge updates into base dict."""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get_settings(self) -> Settings:
        """Get cached settings or load from file."""
        if self._settings is None:
            self._settings = self.load_settings()
        return self._settings

    def load_bookmakers(self) -> BookmakersConfig:
        """Load bookmakers configuration."""
        if self.bookmakers_path.exists():
            with open(self.bookmakers_path, "r") as f:
                data = json.load(f)
            self._bookmakers = BookmakersConfig(**data)
        else:
            self._bookmakers = BookmakersConfig()
        return self._bookmakers

    def get_bookmakers(self) -> BookmakersConfig:
        """Get cached bookmakers config or load from file."""
        if self._bookmakers is None:
            self._bookmakers = self.load_bookmakers()
        return self._bookmakers

    def reload(self) -> None:
        """Force reload all configuration files."""
        self._settings = None
        self._bookmakers = None
        self.load_settings()
        self.load_bookmakers()
