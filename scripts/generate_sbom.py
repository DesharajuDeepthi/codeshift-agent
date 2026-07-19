"""Generate a lightweight CycloneDX-style SBOM from uv.lock and Dockerfiles."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from upgradepilot import __version__


def generate(root: Path) -> dict[str, Any]:
    """Build a CycloneDX-compatible dependency component listing."""
    components: list[dict[str, Any]] = []
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    for package in lock.get("package", []):
        if package.get("name") == "upgradepilot":
            continue
        components.append(
            {
                "type": "library",
                "bom-ref": f"pkg:pypi/{package['name']}@{package['version']}",
                "name": package["name"],
                "version": package["version"],
                "purl": f"pkg:pypi/{package['name']}@{package['version']}",
            }
        )
    for dockerfile in ("Dockerfile", "Dockerfile.ui"):
        text = (root / dockerfile).read_text(encoding="utf-8")
        for image in re.findall(r"^FROM\s+([^\s]+)", text, flags=re.MULTILINE):
            components.append(
                {
                    "type": "container",
                    "bom-ref": f"container:{dockerfile}:{image}",
                    "name": image,
                    "version": image.split(":", 1)[1] if ":" in image else "",
                    "properties": [{"name": "dockerfile", "value": dockerfile}],
                }
            )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:upgradepilot-v1-local-sbom",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "name": "upgradepilot",
                "version": __version__,
            },
            "tools": [
                {
                    "vendor": "UpgradePilot",
                    "name": "scripts/generate_sbom.py",
                    "version": "1.0.0",
                }
            ],
        },
        "components": sorted(components, key=lambda item: (item["type"], item["name"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="docs/security/sbom.cdx.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sbom = generate(root)
    output.write_text(json.dumps(sbom, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output), "components": len(sbom["components"])}))


if __name__ == "__main__":
    main()
