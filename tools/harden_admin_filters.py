#!/usr/bin/env python3
"""Идемпотентно добавляет IsAdmin() в декораторы FSM-хендлеров edit.py / items.py.

Смысл: состояние FSM не должно быть единственной защитой админского флоу.
Dry-run по умолчанию, --apply для записи (с бэкапом .bak).
"""
import re
import shutil
import sys
from pathlib import Path

TARGETS = {
    "functions/edit.py": "ItemEditForm.",
    "functions/items.py": "ItemForm.",
}
DECORATOR = re.compile(r"^@(\w+_router)\.(message|callback_query)\((.*)\)\s*$")

def patch_file(path: Path, state_marker: str, apply: bool) -> int:
    lines = path.read_text().splitlines(keepends=True)
    changed = 0
    for i, line in enumerate(lines):
        m = DECORATOR.match(line.rstrip("\n"))
        if not m or state_marker not in m.group(3) or "IsAdmin" in m.group(3):
            continue
        new = f"@{m.group(1)}.{m.group(2)}({m.group(3)}, IsAdmin())\n"
        print(f"{path}:{i + 1}: {line.rstrip()}\n      -> {new.rstrip()}")
        lines[i] = new
        changed += 1
    if apply and changed:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text("".join(lines))
    return changed

def main() -> int:
    apply = "--apply" in sys.argv
    root = Path(__file__).resolve().parent.parent
    total = 0
    for rel, marker in TARGETS.items():
        p = root / rel
        if not p.exists():
            print(f"SKIP (нет файла): {p}")
            continue
        total += patch_file(p, marker, apply)
    print(f"\n{'применено' if apply else 'DRY-RUN'}: {total} декораторов")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
