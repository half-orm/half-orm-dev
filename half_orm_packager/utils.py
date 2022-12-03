"Various utilities"

import os
import sys

class Color:
    "Colors for the console"
    @staticmethod
    def red(text):
        return f"\033[31m{text}\033[0m"
    @staticmethod
    def green(text):
        return f"\033[32m{text}\033[0m"
    @staticmethod
    def blue(text):
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
