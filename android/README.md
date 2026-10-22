# Herbstchat für Android

Native Android-App (Kotlin + Jetpack Compose), kompatibel zum Herbstchat-Server und Desktop-Client 1.1.2.

- `Crypto.kt` – libsodium (lazysodium): Argon2id, SecretBox, Box, Sicherheitsnummer (identisch zu PyNaCl)
- `Connection.kt` – WebSocket über TLS mit Zertifikat-Pinning (Trust-On-First-Use)
- `ChatCore.kt` – Protokoll und App-Zustand
- `ChatService.kt` – Vordergrund-Dienst für Nachrichten im Hintergrund
- `Store.kt` – Einstellungen, Pins, Sitzung (Android-Keystore), verschlüsseltes Profil
- `Ui.kt` – Oberfläche: Anmelden, Kontakte, Chat, Einstellungen

Bauen: siehe INSTALLATION.md, Teil 3b.
