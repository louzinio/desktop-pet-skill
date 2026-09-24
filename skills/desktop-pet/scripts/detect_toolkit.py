"""Finds which GUI toolkit an app is written with, and where its main window is made.

    python detect_toolkit.py /path/to/app            # a readable report
    python detect_toolkit.py /path/to/app --json     # the same, for a script

Only reads files. It looks at imports, includes and dependency manifests, then points at the
files that construct the top-level window -- the place the pet gets attached.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "env", "build", "dist", "target", "__pycache__",
             ".tox", ".mypy_cache", "vendor", "third_party", "external", ".idea", ".vscode", "out"}
MAX_BYTES = 400_000

# toolkit -> (file suffixes, evidence patterns, main-window patterns)
SIGNS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "qt-python": ((".py",), (r"^\s*(from|import)\s+(PySide6|PySide2|PyQt6|PyQt5)\b", r"^\s*from\s+qtpy\b"),
                  (r"\bQMainWindow\b", r"\.exec_?\(\)", r"QApplication\(")),
    "tk": ((".py",), (r"^\s*(import|from)\s+tkinter\b", r"^\s*(import|from)\s+customtkinter\b", r"^\s*import\s+ttkbootstrap"),
           (r"\bTk\(\)", r"\bCTk\(\)", r"\.mainloop\(\)")),
    "gtk3-python": ((".py",), (r"require_version\(\s*['\"]Gtk['\"]\s*,\s*['\"]3\.0['\"]",),
                    (r"Gtk\.(Application)?Window\(", r"Gtk\.main\(\)")),
    "gtk4-python": ((".py",), (r"require_version\(\s*['\"]Gtk['\"]\s*,\s*['\"]4\.0['\"]", r"\bAdw\.Application"),
                    (r"Gtk\.(Application)?Window\(", r"Adw\.(Application)?Window\(")),
    "wx-python": ((".py",), (r"^\s*import\s+wx\b",), (r"wx\.Frame\b", r"wx\.App\(")),
    "kivy": ((".py", ".kv"), (r"^\s*from\s+kivy\b",), (r"\(App\)", r"\.run\(\)")),
    "terminal-python": ((".py",), (r"^\s*(from|import)\s+(textual|urwid|curses|npyscreen|prompt_toolkit)\b",), (r"\.run\(\)",)),
    "electron": ((".js", ".mjs", ".cjs", ".ts"), (r"require\(['\"]electron['\"]\)", r"from\s+['\"]electron['\"]"),
                 (r"new\s+BrowserWindow\(",)),
    "web": ((".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"),
            (r"ReactDOM\.|createRoot\(", r"createApp\(", r"<script\b", r"@angular/core", r"from\s+['\"]svelte"),
            (r"createRoot\(", r"createApp\(", r"<body\b", r"bootstrapApplication\(")),
    "tauri": ((".rs", ".json", ".toml"), (r"tauri::Builder", r"\"@tauri-apps/"), (r"tauri::Builder",)),
    "qt-cpp": ((".cpp", ".cc", ".cxx", ".h", ".hpp", ".txt", ".pro"),
               (r"#include\s*<Q(Application|MainWindow|Widget)>", r"#include\s*<QtWidgets", r"find_package\(Qt[56]",
                r"QT\s*\+=\s*.*widgets"), (r"\bQMainWindow\b", r"QApplication\s+\w+\(")),
    "qml": ((".qml", ".cpp", ".py"), (r"^\s*import\s+QtQuick", r"QQmlApplicationEngine"), (r"ApplicationWindow\s*\{", r"Window\s*\{")),
    "gtk-c": ((".c", ".h", ".cpp", ".vala", ".txt", ".build"), (r"#include\s*<gtk/gtk\.h>", r"#include\s*<gtkmm", r"dependency\('gtk[34]?",
              r"using\s+Gtk;"), (r"gtk_(application_)?window_new", r"Gtk::(Application)?Window")),
    "wx-cpp": ((".cpp", ".h"), (r"#include\s*<wx/wx\.h>",), (r"wxFrame\b",)),
    "rust-egui": ((".rs", ".toml"), (r"\beframe\b", r"\begui\b"), (r"run_native\(",)),
    "rust-iced": ((".rs", ".toml"), (r"\biced\b",), (r"iced::(application|run)",)),
    "rust-gtk": ((".rs", ".toml"), (r"\bgtk4?\s*=", r"use\s+gtk4?::"), (r"ApplicationWindow",)),
    "rust-slint": ((".rs", ".toml", ".slint"), (r"\bslint\b",), (r"export component",)),
    "go-fyne": ((".go", ".mod"), (r"fyne\.io/fyne",), (r"NewWindow\(",)),
    "java-swing": ((".java", ".kt"), (r"import\s+javax\.swing",), (r"new\s+JFrame\(", r"JFrame\(")),
    "javafx": ((".java", ".kt"), (r"import\s+javafx\.",), (r"extends\s+Application", r"new\s+Stage\(")),
    "compose-desktop": ((".kt",), (r"androidx\.compose\.ui\.window",), (r"\bWindow\(",)),
    "dotnet": ((".cs", ".xaml", ".axaml", ".csproj"), (r"System\.Windows\.Forms", r"<Window\b", r"Avalonia"), (r"\bForm\b", r"<Window\b")),
    "flutter": ((".dart", ".yaml"), (r"package:flutter/",), (r"runApp\(",)),
}

ADAPTERS = {
    "qt-python": "ready: assets/python/desktop_pet/qt.py (WindowPet)",
    "tk": "ready: assets/python/desktop_pet/tk.py (TkPet)",
    "gtk3-python": "ready: assets/python/desktop_pet/gtk.py (GtkPet)",
    "electron": "ready: assets/js/pet-dom.js in the renderer (attachPet)",
    "web": "ready: assets/js/pet-dom.js (attachPet)",
    "tauri": "ready: assets/js/pet-dom.js in the webview (attachPet)",
}


def _files(root: Path):
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.stat().st_size <= MAX_BYTES:
            yield path


def _test_last(path: str) -> tuple[bool, int, str]:
    lowered = path.lower()
    return ("test" in lowered or "example" in lowered or "demo" in lowered, path.count("/"), path)


def scan(root: Path) -> dict:
    evidence: dict[str, list[str]] = defaultdict(list)
    windows: dict[str, list[str]] = defaultdict(list)
    for path in _files(root):
        suffix = path.suffix.lower() if path.name != "CMakeLists.txt" else ".txt"
        texts = None
        for toolkit, (suffixes, signs, window_signs) in SIGNS.items():
            if suffix not in suffixes:
                continue
            if texts is None:
                try:
                    texts = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    break
            if any(re.search(sign, texts, re.MULTILINE) for sign in signs):
                relative = str(path.relative_to(root))
                evidence[toolkit].append(relative)
                if any(re.search(sign, texts, re.MULTILINE) for sign in window_signs):
                    windows[toolkit].append(relative)
    manifest = root / "package.json"
    if manifest.is_file():
        try:
            deps = json.loads(manifest.read_text(encoding="utf-8"))
            names = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
        except (OSError, ValueError, AttributeError):
            names = {}
        if "electron" in names:
            evidence["electron"].append("package.json")
        if any(name.startswith("@tauri-apps/") for name in names):
            evidence["tauri"].append("package.json")
    ranked = sorted(evidence, key=lambda name: -len(evidence[name]))
    return {
        "root": str(root),
        "toolkits": [
            {"toolkit": name, "files": len(evidence[name]), "evidence": evidence[name][:5],
             "main_window_candidates": sorted(windows.get(name, []), key=_test_last)[:8],
             "adapter": ADAPTERS.get(name, "port: see references/toolkits.md, then references/porting.md")}
            for name in ranked
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.root.is_dir():
        print(f"{args.root} is not a directory", file=sys.stderr)
        return 2
    report = scan(args.root.resolve())
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    if not report["toolkits"]:
        print("No GUI toolkit recognised. Read the build files and the entry point by hand.")
        return 1
    for entry in report["toolkits"]:
        print(f"{entry['toolkit']}: {entry['files']} file(s)  ->  {entry['adapter']}")
        for path in entry["evidence"]:
            print(f"    seen in   {path}")
        for path in entry["main_window_candidates"]:
            print(f"    window?   {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
