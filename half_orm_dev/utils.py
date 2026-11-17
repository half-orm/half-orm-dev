import os
import configparser
from pathlib import Path

PWD = os.path.dirname(__file__)
HOP_PATH = os.path.join(PWD)
TEMPLATE_DIRS = os.path.join(HOP_PATH, 'templates')

def hop_version():
    "Returns the version of hop"
    hop_v = None
    with open(os.path.join(HOP_PATH, 'version.txt'), encoding='utf-8') as version:
        hop_v = version.read().strip()
    return hop_v

def is_production_checkout(base_dir) -> bool:
    """Whether `base_dir` is the checkout of a production server.

    Readable without a database connection, which is what the CLI needs
    before it has one. Two marks, either of which is enough -- a production
    server must not be taken for a development machine:

    * ``.hop/production``, written by ``clone --production`` and read by
      the git hooks;
    * ``production = true`` in the connection file, which is what
      half_orm_dev goes by once connected.
    """
    if (Path(base_dir) / '.hop' / 'production').exists():
        return True
    try:
        from half_orm.model import CONF_DIR
        parser = configparser.ConfigParser()
        if not parser.read(os.path.join(CONF_DIR, resolve_database_config_name(base_dir))):
            return False
        return parser.getboolean('database', 'production', fallback=False)
    except (configparser.Error, ValueError, OSError):
        return False


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
        config = configparser.ConfigParser()
        # Let configparser.Error propagate: a malformed config file is a real
        # error and silently falling back to the directory name would cause a
        # wrong database connection without any warning.
        config.read(config_path)
        if config.has_option('halfORM', 'package_name'):
            package_name = config.get('halfORM', 'package_name')
            if package_name:
                return package_name

    # Priority 3: directory name
    return base_path.name
