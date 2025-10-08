import os
import json
from .constants import REDACTION_CONFIG_FILE
from .logger import get_logger

logger = get_logger(__name__)

class RedactionConfig:
    """Load and provide redaction config (how many digits to keep)."""

    def __init__(self, path=REDACTION_CONFIG_FILE):
        self.path = path
        self.cfg = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.exception("RedactionConfig._load: failed to read config file %s", self.path)
                # fall through to defaults
        return {"id": {"left_keep": 2, "right_keep": 2},
                "phone": {"left_keep": 4, "right_keep": 2}}

    def get_keep(self, kind: str):
        return (int(self.cfg.get(kind, {}).get("left_keep", 0)),
                int(self.cfg.get(kind, {}).get("right_keep", 0)))

    def get_exclusion(self, key: str, default=None):
        """Return exclusion settings for a given key (e.g., 'imei').

        Returns the raw dictionary from config or the provided default.
        """
        return self.cfg.get("exclude", {}).get(key, default)