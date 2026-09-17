"""Load runtime YAML and branding JSON without shallowly dropping settings."""
from pathlib import Path
import json
import yaml

def load_configuration(pipeline_dir, filename="config/config.yaml"):
    root = Path(pipeline_dir)
    path = root / filename
    config = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    config = config or {}
    branding = root.parent / "blog.config.json"
    if branding.exists():
        data = json.loads(branding.read_text(encoding="utf-8"))
        site = data.get("site", {})
        config.setdefault("site", {}).update(site)
        if site.get("name"):
            config["site"]["title"] = site["name"]
        config.setdefault("telegram", {}).update(data.get("telegram", {}))
        if data.get("blogId"):
            config["blogId"] = data["blogId"]
        ai = data.get("ai", {})
        if ai.get("model"):
            config.setdefault("agent", {})["model_name"] = ai["model"]
        if ai.get("provider"):
            config.setdefault("engine", {})["provider"] = ai["provider"]
    return config
