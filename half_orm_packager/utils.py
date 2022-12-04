"Various utilities"

import os

class Color:
    "Colors for the console"
    @staticmethod
    def red(text):
        "red"
        return f"\033[31m{text}\033[0m"
    @staticmethod
    def green(text):
        "green"
        return f"\033[32m{text}\033[0m"
    @staticmethod
    def blue(text):
        "blue"
        return f"\033[34m{text}\033[0m"

HOP_PATH = os.path.dirname(__file__)
TEMPLATE_DIRS = os.path.join(HOP_PATH, 'templates')

BEGIN_CODE = "#>>> PLACE YOUR CODE BELLOW THIS LINE. DO NOT REMOVE THIS LINE!\n"
END_CODE = "#<<< PLACE YOUR CODE ABOVE THIS LINE. DO NOT REMOVE THIS LINE!\n"

def read(file_):
    "Read file helper"
    with open(file_, encoding='utf-8') as text_io_wrapper:
        return text_io_wrapper.read()

def write(file_, data):
    "Write file helper"
    with open(file_, 'w', encoding='utf-8') as text_io_wrapper:
        return text_io_wrapper.write(data)

def hop_version():
    "Returns the version of hop"
    hop_v = None
    with open(os.path.join(HOP_PATH, 'version.txt'), encoding='utf-8') as version:
        hop_v = version.read().strip()
    return hop_v
