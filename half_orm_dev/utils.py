import os

PWD = os.path.dirname(__file__)
HOP_PATH = os.path.join(PWD)
TEMPLATE_DIRS = os.path.join(HOP_PATH, 'templates')

def hop_version():
    "Returns the version of hop"
    hop_v = None
    with open(os.path.join(HOP_PATH, 'version.txt'), encoding='utf-8') as version:
        hop_v = version.read().strip()
    return hop_v
