# Herbstchat 1.0.0

Privater, Ende-zu-Ende-verschlüsselter Messenger.

## Downloads

| Datei | Plattform |
|---|---|
| `Herbstchat-1.0.0.apk` | Android 8.0 oder neuer |
| `Herbstchat-Windows.exe` | Windows 10/11 |
| `Herbstchat-macOS.zip` | macOS 11+ (beim ersten Öffnen: Rechtsklick → „Öffnen“) |
| `Herbstchat-Linux-x86_64` | Linux x86_64 (`chmod +x` und starten) |
| `herbstchat-server_1.0.0_all.deb` | Server für Debian Testing, arm64 und amd64 |

Die Clients brauchen kein installiertes Python. Server: `chat.example.org`, Port `47474`, ist schon voreingestellt.

## Neu in dieser Version

- Android-App (Kotlin, Jetpack Compose), voll kompatibel mit Server und Desktop-Client
- Gleiche Verschlüsselung auf allen Geräten: Argon2id, X25519, XSalsa20-Poly1305 (libsodium)
- Android: angemeldet bleiben (Schlüssel im Android-Keystore), Nachrichten im Hintergrund, Benachrichtigungen, helles/dunkles Design

Installationsanleitung: siehe `INSTALLATION.md`.
