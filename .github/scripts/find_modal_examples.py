#!/usr/bin/env python3
import os
import json


def is_modal_script(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return "@modal." in content or "modal.App()" in content
    except Exception:
        return False


def format_path(path):
    return path.replace("/", ".").replace(".py", "")


modal_scripts = []
for dirpath, _, filenames in os.walk("src"):
    for file in filenames:
        if file.endswith(".py"):
            full_path = os.path.join(dirpath, file)
            if is_modal_script(full_path):
                modal_scripts.append(format_path(full_path))

print(json.dumps({"example": modal_scripts}))
