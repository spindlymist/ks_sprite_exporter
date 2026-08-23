# Run with Python 3

import os
import sys
import shutil

if not os.path.isdir("./build"):
    print("No build directory. Run python build.py build first")
    sys.exit()

build_dir = None
for name in os.listdir("./build"):
    if not name.startswith("lib"):
        continue
    path = os.path.join("./build/", name)
    if os.path.isdir(path):
        build_dir = path
        break

if not build_dir:
    print("No build directory. Run python build.py build first")

shutil.copytree(os.path.join(build_dir, "mmfparser"), "./mmfparser", dirs_exist_ok=True)
