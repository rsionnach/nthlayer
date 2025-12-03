"""
NthLayer configuration management.

Handles global and per-service configuration options.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ErrorBudgetConfig:
    """Error budget configuration."""
    
    inherited_attribution: bool = False  # Default: OFF for startups
    min_correlation_confidence: float = 0.8
    time_window_minutes: int = 5


@dataclass
class NthLayerConfig:
    """Global NthLayer configuration."""
    
    error_budget: ErrorBudgetConfig
    
    @classmethod
    def load(cls, config_file: str | Path | None = None) -> NthLayerConfig:
        """
        Load configuration from file or defaults.
        
        Search order:
        1. Provided config_file
        2. .nthlayer/config.yaml (cwd)
        3. ~/.nthlayer/config.yaml (home)
        4. Defaults
        
        Args:
            config_file: Optional explicit config file path
        
        Returns:
            NthLayerConfig instance
        """
        # Try explicit path first
        if config_file:
            config_path = Path(config_file)
            if config_path.exists():
                return cls._load_from_file(config_path)
        
        # Try .nthlayer/config.yaml in cwd
        cwd_config = Path.cwd() / ".nthlayer" / "config.yaml"
        if cwd_config.exists():
            return cls._load_from_file(cwd_config)
        
        # Try ~/.nthlayer/config.yaml
        home_config = Path.home() / ".nthlayer" / "config.yaml"
        if home_config.exists():
            return cls._load_from_file(home_config)
        
        # Use defaults
        return cls(
            error_budget=ErrorBudgetConfig(),
        )
    
    @classmethod
    def _load_from_file(cls, path: Path) -> NthLayerConfig:
        """Load config from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        
        error_budget_data = data.get("error_budget", {})
        
        return cls(
            error_budget=ErrorBudgetConfig(
                inherited_attribution=error_budget_data.get("inherited_attribution", False),
                min_correlation_confidence=error_budget_data.get("min_correlation_confidence", 0.8),
                time_window_minutes=error_budget_data.get("time_window_minutes", 5),
            ),
        )
    
    def save(self, path: str | Path) -> None:
        """Save configuration to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "error_budget": {
                "inherited_attribution": self.error_budget.inherited_attribution,
                "min_correlation_confidence": self.error_budget.min_correlation_confidence,
                "time_window_minutes": self.error_budget.time_window_minutes,
            },
        }
        
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_config() -> NthLayerConfig:
    """
    Get current NthLayer configuration.
    
    Convenience function for loading config with default search.
    """
    return NthLayerConfig.load()
