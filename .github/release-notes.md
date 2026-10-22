# Herbstchat @VERSION@

Privater, Ende-zu-Ende-verschlüsselter Messenger.

## Downloads

| Datei | Plattform |
|---|---|
| `Herbstchat-@VERSION@.apk` | Android 8.0 oder neuer |
| `Herbstchat-Windows.exe` | Windows 10/11 |
| `Herbstchat-macOS.zip` | macOS 11+ (beim ersten Öffnen: Rechtsklick → „Öffnen“) |
| `Herbstchat-Linux-x86_64` | Linux x86_64 (`chmod +x` und starten) |
| `herbstchat-server_@VERSION@_all.deb` | Server für Debian/Ubuntu, arm64 und amd64 |

Die Clients brauchen kein installiertes Python. Server: `chat.example.org`, Port `47474`, ist schon voreingestellt.

## Neu in dieser Version

- **Chatverlauf wird über alle Geräte synchronisiert** – gesendete und empfangene Nachrichten, auch die auf anderen Geräten gesendeten (live)
- Der Server speichert dafür nur den Chiffretext, Inhalte bleiben Ende-zu-Ende-verschlüsselt
- Bestehender lokaler Verlauf wird beim ersten Start einmalig hochgeladen
- „Verlauf löschen“ löscht jetzt auch auf dem Server (und damit auf allen Geräten)
- Neues Admin-Web mit Seitenleiste und Debug-Seite
- Dunkles Design als Standard
- Behoben: Server-Login schlug mit 1.1.0/1.1.1 immer fehl, doppelte Verlaufseinträge, Debug-Seite

**Wichtig:** Server und alle Clients gemeinsam auf @VERSION@ aktualisieren. Clients 1.1.0 bitte nicht weiter verwenden.

Installationsanleitung: siehe `INSTALLATION.md`.
