import re
import os

ID_REGEX = re.compile(r"(\b\d{9}\b|\b\d{12}\b)")
PHONE_REGEX = re.compile(r"(\b(?:84|0)\d{9}\b)")
KNOWLEDGE_BASE_FILE = "customer_redaction_rules.json"
REDACTION_CONFIG_FILE = "redaction_config.json"
DEFAULT_CUSTOMER_KEYWORDS = [
    "khách hàng", "bên mua", "bên b", "bên được bảo hiểm", "người mua"
]