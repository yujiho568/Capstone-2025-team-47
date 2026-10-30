import os, json
def ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)
def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
