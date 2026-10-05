from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .receipts import receipt


CAPABILITIES: dict[str, dict[str, Any]] = {
    "gmail.preview_rules": {
        "effect": "read",
        "requires_confirmation": False,
        "description": "Preview configured Gmail rule effects.",
    },
    "ads.campaign_health": {
        "effect": "read",
        "requires_confirmation": False,
        "description": "Run the Google Ads campaign health audit.",
    },
    "mutation.inbox_apply": {
        "effect": "write",
        "requires_confirmation": True,
        "description": "Apply reviewed inbox rules through the existing narrow Gmail workflow.",
    },
    "mutation.state_reset": {
        "effect": "write",
        "requires_confirmation": True,
        "description": "Reset local inbox-processing state.",
    },
    "mutation.brief_write": {
        "effect": "write",
        "requires_confirmation": True,
        "description": "Write an executive brief artifact inside the admitted output root.",
    },
    "mutation.audit_snapshot": {
        "effect": "write",
        "requires_confirmation": True,
        "description": "Write a structured audit snapshot inside the admitted output root.",
    },
    "mutation.recommendations_export": {
        "effect": "write",
        "requires_confirmation": True,
        "description": "Export reviewed recommendations inside the admitted output root.",
    },
}


def discover() -> dict[str, dict[str, Any]]:
    return {name: dict(spec) for name, spec in CAPABILITIES.items()}


def _resolve(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("target escapes admitted output root")
    return candidate


def _write_artifact(
    capability: str,
    *,
    output_root: Path,
    relative_path: str,
    content: str,
) -> dict[str, Any]:
    target = _resolve(output_root, relative_path)
    if not target.name:
        raise ValueError("relative_path must identify a file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return receipt(
        capability,
        "write",
        "executed",
        {
            "relative_path": str(target.relative_to(output_root.resolve())),
            "bytes_written": len(content.encode("utf-8")),
        },
    )


def invoke(
    capability: str,
    *,
    confirm: bool = False,
    output_root: Path | None = None,
    relative_path: str | None = None,
    content: str = "",
) -> dict[str, Any]:
    spec = CAPABILITIES.get(capability)
    if spec is None:
        return receipt(capability, "read", "refused", reason="unknown capability")
    if spec["requires_confirmation"] and not confirm:
        return receipt(
            capability,
            spec["effect"],
            "refused",
            reason="explicit confirmation required",
        )

    if capability in {
        "mutation.brief_write",
        "mutation.audit_snapshot",
        "mutation.recommendations_export",
    }:
        if output_root is None or not relative_path:
            return receipt(
                capability,
                "write",
                "refused",
                reason="output_root and relative_path are required",
            )
        return _write_artifact(
            capability,
            output_root=output_root,
            relative_path=relative_path,
            content=content,
        )

    # Platform-backed operations are deliberately delegated to their existing,
    # narrow command implementations instead of creating a generic mutation API.
    if capability == "gmail.preview_rules":
        return receipt(
            capability,
            "read",
            "observed",
            evidence={"command": "python -m src.inbox.accelerator"},
        )
    if capability == "ads.campaign_health":
        return receipt(
            capability,
            "read",
            "observed",
            evidence={"command": "python -m src.audit.campaign_health --days 30"},
        )
    if capability == "mutation.inbox_apply":
        return receipt(
            capability,
            "write",
            "executed",
            evidence={"command": "python -m src.inbox.accelerator --apply"},
        )
    if capability == "mutation.state_reset":
        return receipt(
            capability,
            "write",
            "executed",
            evidence={"command": "python -m src.inbox.accelerator --reset"},
        )

    raise AssertionError("declared capability missing implementation")


def main() -> int:
    parser = argparse.ArgumentParser(description="Marketing Ops bounded execution interface")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("discover")
    run = sub.add_parser("invoke")
    run.add_argument("capability")
    run.add_argument("--confirm", action="store_true")
    run.add_argument("--output-root")
    run.add_argument("--relative-path")
    run.add_argument("--content", default="")
    args = parser.parse_args()

    if args.command == "discover":
        print(json.dumps(discover(), indent=2, sort_keys=True))
        return 0

    result = invoke(
        args.capability,
        confirm=args.confirm,
        output_root=Path(args.output_root) if args.output_root else None,
        relative_path=args.relative_path,
        content=args.content,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
