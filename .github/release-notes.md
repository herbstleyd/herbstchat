# Herbstchat @VERSION@

Privater, Ende-zu-Ende-verschlüsselter Messenger mit eigenem Server.

## Downloads

| Datei | Plattform |
|---|---|
| `Herbstchat-@VERSION@.apk` | Android 8.0 oder neuer |
| `Herbstchat-Windows.exe` | Windows 10/11 |
| `Herbstchat-macOS.zip` | macOS 11+ (beim ersten Öffnen: Rechtsklick, dann „Öffnen“) |
| `Herbstchat-Linux-x86_64` | Linux x86_64 (`chmod +x` und starten) |
| `herbstchat-server_@VERSION@_all.deb` | Server für Debian/Ubuntu, arm64 und amd64 |

Die Clients brauchen kein installiertes Python. Beim ersten Start die Adresse des eigenen Servers eintragen (Standard-Port `47474`).

## Neu in dieser Version

- Neues Design in Blau (`#0066cc`) statt Orange, kühlere Farben im hellen und dunklen Design
- Neue Akzentfarben: Herbstchat-Blau, Himmelblau, Petrol, Waldgrün, Violett, Ahorn-Rot
- Keine voreingestellte Serveradresse mehr: Jeder trägt seinen eigenen Server ein
- Server-Paket: `public_address` in `server.conf` ist leer; das TLS-Zertifikat wird auf diese Adresse oder den Rechnernamen ausgestellt
- Ausführliche README, Lizenz 0BSD

## Aus 1.1.2

- Chatverlauf wird über alle Geräte synchronisiert, der Server speichert nur Chiffretext
- „Verlauf löschen“ löscht auch auf dem Server und damit auf allen Geräten
- Admin-Web mit Seitenleiste und Debug-Seite

**Hinweis:** Server und Clients möglichst gemeinsam auf @VERSION@ aktualisieren. Bestehende Einstellungen (Serveradresse, Konto) bleiben erhalten.

Installationsanleitung: siehe `INSTALLATION.md`.
