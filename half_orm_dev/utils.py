import os
from pathlib import Path
from configparser import ConfigParser

PWD = os.path.dirname(__file__)
HOP_PATH = os.path.join(PWD)
TEMPLATE_DIRS = os.path.join(HOP_PATH, 'templates')

def hop_version():
    "Returns the version of hop"
    hop_v = None
    with open(os.path.join(HOP_PATH, 'version.txt'), encoding='utf-8') as version:
        hop_v = version.read().strip()
    return hop_v

def resolve_database_config_name(base_dir):
    """
    Resolve database configuration name with backward compatibility.

    Priority:
    1. .hop/alt_config if exists → use content
    2. .hop/config[halfORM][package_name] if exists → use it (backward compat)
    3. Otherwise → use directory name
    """

    base_path = Path(base_dir)

    # Priority 1: alt_config
    alt_config_path = base_path / '.hop' / 'alt_config'
    if alt_config_path.exists():
        content = alt_config_path.read_text().strip()
        if content:
            return content

    # Priority 2: package_name in .hop/config (backward compat)
    config_path = base_path / '.hop' / 'config'
    if config_path.exists():
        config = ConfigParser()
        try:
            config.read(config_path)
            if config.has_option('halfORM', 'package_name'):
                package_name = config.get('halfORM', 'package_name')
                if package_name:
                    return package_name
        except Exception:
            pass

    # Priority 3: directory name
    return base_path.name
