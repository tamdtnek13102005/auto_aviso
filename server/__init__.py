"""
Auto Aviso - Server Package
Config trung tâm nằm ở server/config.py
"""

# Re-export từ config để tiện import
from .config import (
    AGENT_URL,
    SERVER_HOST,
    SERVER_PORT,
    BASE_URL,
    TEMPLATES_DIR,
    API_ENDPOINTS,
    print_api_info,
)
