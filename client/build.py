#!/usr/bin/env python3
"""Baut eine eigenstaendige Herbstchat-App mit PyInstaller fuer das aktuelle Betriebssystem.
   Windows: dist/Herbstchat.exe | macOS: dist/Herbstchat.app | Linux: dist/Herbstchat"""
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "pyinstaller"])
args = ["--noconfirm", "--windowed", "--name", "Herbstchat", "--collect-all", "nacl", "--hidden-import", "_cffi_backend", "--collect-binaries", "cffi",
        "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtQml"]
if sys.platform != "darwin":
    args.append("--onefile")
if sys.platform == "darwin":
    args += ["--osx-bundle-identifier", "org.herbstleyd.herbstchat"]
subprocess.check_call([sys.executable, "-m", "PyInstaller", *args, "herbstchat.py"])
print("Fertig - siehe Ordner dist/")
