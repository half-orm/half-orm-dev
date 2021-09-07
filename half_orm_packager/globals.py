import os

HOP_PATH = os.path.dirname(__file__)
TEMPLATES_DIR = f'{HOP_PATH}/templates'

def hop_version():
    return open(f'{HOP_PATH}/version.txt').read().strip()
