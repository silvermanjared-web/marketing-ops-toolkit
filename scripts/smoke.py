from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.execution.bounded import discover


def main() -> int:
    registry = discover()
    writes = [name for name, spec in registry.items() if spec["effect"] == "write"]
    assert len(writes) == 5, writes
    assert all(registry[name]["requires_confirmation"] for name in writes)
    print("marketing ops toolkit smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
