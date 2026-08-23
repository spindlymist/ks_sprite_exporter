# Run with Python 3

import glob
import os
import shutil

for path in glob.glob("./**/*.pyx", recursive=True):
    (prefix, _) = os.path.splitext(path)
    cpp = prefix + ".cpp"
    if os.path.isfile(cpp):
        os.unlink(cpp)
    pyd = prefix + ".pyd"
    if os.path.isfile(pyd):
        os.unlink(pyd)

for path in glob.glob("./**/*.pyc", recursive=True):
    if os.path.isfile(path):
        os.unlink(path)

for path in glob.glob("./**/__pycache__", recursive=True):
    if os.path.isdir(path):
        shutil.rmtree(path)

if os.path.isdir("./build"):
    shutil.rmtree("./build")
