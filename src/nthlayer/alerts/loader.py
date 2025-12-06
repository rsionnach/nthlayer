"""
Alert Template Loader

Loads alerting rules from awesome-prometheus-alerts templates.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .models import AlertRule

logger = logging.getLogger(__name__)


class AlertTemplateLoader:
    """
    Load alerting rules from awesome-prometheus-alerts templates.

    Templates are organized by technology:
        templates/databases/postgres.yaml
        templates/databases/mysql.yaml
        templates/proxies/nginx.yaml
        etc.

    Usage:
        loader = AlertTemplateLoader()
        alerts = loader.load_technology("postgres")
        # Returns List[AlertRule] for PostgreSQL
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize loader.

        Args:
            templates_dir: Path to templates directory.
                          Defaults to ./templates relative to this file.
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"

        self.templates_dir = Path(templates_dir)
        self.cache: Dict[str, List[AlertRule]] = {}

        logger.info(f"Initialized AlertTemplateLoader with templates_dir={self.templates_dir}")

    def load_technology(self, technology: str) -> List[AlertRule]:
        """
        Load alerts for a specific technology.

        Args:
            technology: Technology name (e.g., "postgres", "redis", "nginx")

        Returns:
            List of AlertRule objects for that technology

        Raises:
            ValueError: If technology not found
        """
        # Check cache first
        if technology in self.cache:
            logger.debug(f"Returning cached alerts for {technology}")
            return self.cache[technology]

        # Find template file
        template_file = self._find_template(technology)
        if not template_file:
            logger.warning(f"No template found for technology: {technology}")
            return []

        # Load and parse
        alerts = self._load_from_file(template_file, technology)

        # Cache results
        self.cache[technology] = alerts

        logger.info(f"Loaded {len(alerts)} alerts for {technology} from {template_file}")
        return alerts

    def _find_template(self, technology: str) -> Optional[Path]:
        """
        Find template file for a technology.

        Searches across all categories (databases, proxies, orchestrators, etc.)
        with fuzzy matching (postgres, postgresql, pg all match postgres.yaml)
        """
        # Normalize technology name
        tech_lower = technology.lower()

        # Common aliases
        aliases = {
            "pg": "postgres",
            "postgresql": "postgres",
            "mysql": "mysql",
            "mariadb": "mysql",
            "mongo": "mongodb",
            "mongodb": "mongodb",
            "k8s": "kubernetes",
            "kubernetes": "kubernetes",
        }

        # Try alias first
        if tech_lower in aliases:
            tech_lower = aliases[tech_lower]

        # Search for exact match
        for category_dir in self.templates_dir.iterdir():
            if not category_dir.is_dir():
                continue

            template_file = category_dir / f"{tech_lower}.yaml"
            if template_file.exists():
                return template_file

        # Try fuzzy match
        for category_dir in self.templates_dir.iterdir():
            if not category_dir.is_dir():
                continue

            for template_file in category_dir.glob("*.yaml"):
                if tech_lower in template_file.stem.lower():
                    return template_file

        return None

    def _load_from_file(self, template_file: Path, technology: str) -> List[AlertRule]:
        """
        Load alerts from a YAML template file.

        Expected format (awesome-prometheus-alerts):
            groups:
              - name: <technology>
                rules:
                  - alert: AlertName
                    expr: <promql>
                    for: 5m
                    labels:
                      severity: critical
                    annotations:
                      summary: Alert summary
                      description: Alert description
        """
        try:
            with open(template_file) as f:
                data = yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError, OSError) as e:
            logger.error(f"Failed to load {template_file}: {e}")
            return []

        # Determine category from parent directory
        category = template_file.parent.name

        # Parse rules
        alerts = []
        for group in data.get("groups", []):
            for rule_dict in group.get("rules", []):
                if "alert" not in rule_dict:
                    # Skip recording rules (not alerts)
                    continue

                try:
                    alert = AlertRule.from_dict(rule_dict, technology=technology, category=category)
                    alerts.append(alert)
                except (KeyError, ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse alert {rule_dict.get('alert')}: {e}")

        return alerts

    def list_available_technologies(self) -> List[str]:
        """
        List all available technologies with templates.

        Returns:
            List of technology names (e.g., ["postgres", "redis", "nginx"])
        """
        technologies = []

        for category_dir in self.templates_dir.iterdir():
            if not category_dir.is_dir():
                continue

            for template_file in category_dir.glob("*.yaml"):
                tech = template_file.stem
                technologies.append(tech)

        return sorted(technologies)

    def get_category_for_technology(self, technology: str) -> Optional[str]:
        """
        Get the category (databases, proxies, etc.) for a technology.

        Args:
            technology: Technology name

        Returns:
            Category name or None if not found
        """
        template_file = self._find_template(technology)
        if template_file:
            return template_file.parent.name
        return None
