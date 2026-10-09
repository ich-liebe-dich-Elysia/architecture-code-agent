"""Build the desktop executable, including Conda's external runtime DLLs."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def runtime_binaries() -> list[Path]:
    """Collect Conda libraries and their local dependencies by PE imports."""
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    if os.name != "nt" or not conda_bin.is_dir():
        return []

    import pefile  # Installed by PyInstaller on Windows.

    lookup: dict[str, Path] = {}
    search_roots = [conda_bin, Path(sys.base_prefix) / "DLLs", Path(sys.base_prefix)]
    for directory in search_roots:
        if directory.is_dir():
            for path in directory.iterdir():
                if path.is_file() and path.suffix.lower() == ".dll":
                    lookup.setdefault(path.name.lower(), path)

    names = (
        "libcrypto-3-x64.dll", "libssl-3-x64.dll", "liblzma.dll", "libbz2.dll",
        "ffi.dll", "tcl86t.dll", "tk86t.dll", "zlib.dll", "vcruntime140.dll",
        "vcruntime140_1.dll", "msvcp140.dll",
    )
    pending = [lookup[name] for name in names if name in lookup]
    collected: dict[str, Path] = {}
    import_tables = [
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"],
    ]
    while pending:
        path = pending.pop()
        name = path.name.lower()
        if name in collected:
            continue
        collected[name] = path
        with pefile.PE(str(path), fast_load=True) as binary:
            binary.parse_data_directories(directories=import_tables)
            imports = list(getattr(binary, "DIRECTORY_ENTRY_IMPORT", []))
            imports.extend(getattr(binary, "DIRECTORY_ENTRY_DELAY_IMPORT", []))
            for imported in imports:
                dependency = lookup.get(imported.dll.decode("ascii").lower())
                if dependency is not None and dependency.name.lower() not in collected:
                    pending.append(dependency)
    return [collected[name] for name in sorted(collected)]


def main() -> int:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
        "--windowed", "--name", "ArchitectureAgent", "--distpath", str(ROOT),
        "--workpath", str(ROOT / ".build" / "pyinstaller"),
        "--specpath", str(ROOT / ".build"),
    ]
    binaries = runtime_binaries()
    for binary in binaries:
        command.extend(["--add-binary", f"{binary}{os.pathsep}."])
    command.append(str(ROOT / "desktop_entry.py"))

    environment = os.environ.copy()
    conda_bin = Path(sys.base_prefix) / "Library" / "bin"
    if conda_bin.is_dir():
        environment["PATH"] = str(conda_bin) + os.pathsep + environment.get("PATH", "")
    print("Bundling runtime DLLs:", ", ".join(path.name for path in binaries) or "standard Python runtime", flush=True)
    return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
