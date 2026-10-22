<div align="center">

# 🍂 Herbstchat

**Privater Instant Messenger mit Ende-zu-Ende-Verschlüsselung**

Eigener Server · Desktop-Apps für Windows, macOS und Linux · Android-App

[![Release](https://img.shields.io/github/v/release/herbstleyd/herbstchat?label=Version&color=c8641e)](https://github.com/herbstleyd/herbstchat/releases/latest)
![Plattformen](https://img.shields.io/badge/Plattformen-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Android-555)
![Verschlüsselung](https://img.shields.io/badge/E2EE-X25519%20%2B%20XSalsa20--Poly1305-3bb54a)

<!-- SCREENSHOT: Hauptfenster Desktop (z. B. docs/screenshots/desktop-hauptfenster.png) -->
<!-- ![Herbstchat Desktop](docs/screenshots/desktop-hauptfenster.png) -->

</div>

---

## Inhalt

- [Was ist Herbstchat?](#was-ist-herbstchat)
- [Funktionen](#funktionen)
- [Download](#download)
- [Schnellstart](#schnellstart)
- [So funktioniert die Verschlüsselung](#so-funktioniert-die-verschlüsselung)
- [Was der Server weiß und was nicht](#was-der-server-weiß-und-was-nicht)
- [Chatverlauf auf mehreren Geräten](#chatverlauf-auf-mehreren-geräten)
- [Der Server](#der-server)
- [Die Admin-Oberfläche](#die-admin-oberfläche)
- [Desktop-Client](#desktop-client)
- [Android-App](#android-app)
- [Projektstruktur](#projektstruktur)
- [Selbst bauen](#selbst-bauen)
- [Grenzen und Hinweise](#grenzen-und-hinweise)
- [Häufige Fragen](#häufige-fragen)

---

## Was ist Herbstchat?

Herbstchat ist ein kleiner, privater Messenger für Familie, Freunde oder ein Team. Den Server betreibt man **selbst**, zum Beispiel auf einem Raspberry Pi oder einem kleinen Debian/Ubuntu-Server zu Hause. Die Apps verbinden sich über eine TLS-Verbindung mit diesem Server.

Jede Nachricht wird **auf dem Gerät des Absenders verschlüsselt** und erst auf dem Gerät des Empfängers wieder entschlüsselt. Der Server leitet nur Daten weiter, die er selbst nicht lesen kann. Das gilt auch für den Administrator: Nachrichteninhalte und Passwörter bekommt er nie zu sehen.

Optisch und vom Gefühl her orientiert sich Herbstchat an den klassischen Messengern der 2000er (Kontaktliste, Online-Status, „Uh-oh“-Ton), nutzt aber moderne Kryptografie.

---

## Funktionen

### Für Nutzer

- 🔒 **Ende-zu-Ende-Verschlüsselung** für alle Nachrichten (NaCl/libsodium)
- 👥 **Kontaktliste** mit Suche nach Nicknamen, Hinzufügen und Entfernen
- 🟢 **Online-Status:** Online, Abwesend, Beschäftigt, Unsichtbar
- ✉️ **Offline-Nachrichten:** Nachrichten an Kontakte, die gerade offline sind, werden verschlüsselt zwischengespeichert und beim nächsten Login zugestellt
- ✍️ **Tipp-Anzeige** („schreibt …“), abschaltbar
- ✓ **Zustellstatus** pro Nachricht: wird gesendet ⏳, gesendet ✓, wartet auf Empfänger ✉, fehlgeschlagen ⚠
- 🔁 **Chatverlauf auf allen Geräten:** Desktop und Handy zeigen denselben Verlauf, auch für selbst gesendete Nachrichten
- 🛡️ **Sicherheitsnummer** zum Prüfen eines Kontakts und eigener **Schlüssel-Fingerabdruck**
- ⚠️ **Warnung bei Schlüsselwechsel** (Desktop): Ändert sich der Schlüssel eines Kontakts, erscheint ein Hinweis im Chat
- 📌 **Zertifikat-Pinning** (Trust-On-First-Use) gegen Man-in-the-Middle-Angriffe
- 🔔 **Benachrichtigungen** mit optionaler Vorschau, Töne, Taskleisten-Blinken, Tray-Symbol
- 🎨 **Dunkles und helles Design**, Akzentfarbe, Schriftart und -größe einstellbar
- 🔑 **Passwort und E-Mail-Adresse ändern** direkt in der App

### Für den Betreiber

- 📦 **Debian-Paket** mit systemd-Dienst, automatisch erzeugtem TLS-Zertifikat und Admin-Zugang
- 🖥️ **Admin-Weboberfläche** (nur im lokalen Netz): Dashboard, Benutzerverwaltung, Rundschreiben, Einstellungen, Protokoll, Debug
- 🚫 **Moderation:** Timeout, Bann, Stummschalten, Verbindung trennen, Nickname/E-Mail ändern, Account löschen
- 📢 **Systemnachrichten** an einzelne oder alle Nutzer, optional zusätzlich per E-Mail (SMTP)
- 📝 **Nachricht des Tages** beim Login und **Registrierung schließen** auf Knopfdruck
- 🧱 **Schutz vor Brute-Force:** 10 Fehlversuche innerhalb von 10 Minuten sperren die IP-Adresse vorübergehend

<!-- SCREENSHOT: Kontaktliste + Chat (docs/screenshots/desktop-chat.png) -->

---

## Download

Alle fertigen Dateien gibt es unter **[Releases](https://github.com/herbstleyd/herbstchat/releases/latest)**:

| Datei | Wofür |
|---|---|
| `herbstchat-server_<VERSION>_all.deb` | Server für Debian/Ubuntu/Raspberry Pi OS (läuft auf jeder Architektur) |
| `Herbstchat-Windows.exe` | Desktop-Client für Windows 10/11 (eine einzelne Datei, keine Installation) |
| `Herbstchat-macOS.zip` | Desktop-Client für macOS (App-Bundle) |
| `Herbstchat-Linux-x86_64` | Desktop-Client für Linux x86_64 (eine einzelne Datei) |
| `Herbstchat-<VERSION>.apk` | Android-App (ab Android 8.0) |

> **Wichtig:** Server und Clients sollten immer **dieselbe Version** haben. Nach einem Server-Update bitte auch alle Apps aktualisieren.

---

## Schnellstart

### 1. Server installieren (Debian/Ubuntu)

```bash
sudo apt install ./herbstchat-server_*_all.deb
```

Das Paket richtet alles automatisch ein und startet den Dienst. Danach:

```bash
# Admin-Zugang für die Weboberfläche
sudo cat /etc/herbstchat/admin-zugang.txt

# Fingerabdruck des TLS-Zertifikats (zum Vergleichen beim ersten Verbinden)
sudo cat /etc/herbstchat/zertifikat-fingerabdruck.txt

# Status prüfen
sudo systemctl status herbstchat-server
```

Im Router muss nur **TCP-Port 47474** an den Server weitergeleitet werden. Den Admin-Port 8088 bitte **nicht** freigeben.

### 2. App starten und Konto anlegen

1. App starten (Windows: Doppelklick auf die `.exe`, Linux: `chmod +x` und starten, macOS: ZIP entpacken und App öffnen).
2. Serveradresse und Port eintragen (Standard: `chat.example.org:47474`).
3. Auf **Registrieren** wechseln, E-Mail, Nickname und ein **gutes Passwort** eingeben.
4. Beim ersten Verbinden wird der Zertifikat-Fingerabdruck angezeigt. Mit dem Wert vom Server vergleichen und bestätigen.
5. Über **Kontakt hinzufügen** (Strg+N) Freunde per Nickname suchen und losschreiben.

Eine ausführliche Anleitung mit Update, Deinstallation und Bauen aus dem Quellcode steht in **[INSTALLATION.md](INSTALLATION.md)**.

<!-- SCREENSHOT: Login-/Registrierungsfenster (docs/screenshots/login.png) -->

---

## So funktioniert die Verschlüsselung

Herbstchat verwendet ausschließlich bewährte Bausteine aus **[libsodium](https://libsodium.org)** (Desktop: PyNaCl, Android: lazysodium). Es gibt keine selbst erfundene Kryptografie.

### Überblick

```
   Passwort
      │
      ▼
 ┌──────────┐   Salt (pro Benutzer, 16 Byte)
 │ Argon2id │◄──────────────────────────────
 └────┬─────┘
      │ 64 Byte
      ├──────────────────────────┐
      ▼                          ▼
 Auth-Schlüssel (32 B)     Tresor-Schlüssel (32 B)
 → wird an den Server      → verlässt das Gerät NIE
   gesendet (Login)          │
                             ▼
                   verschlüsselt den privaten
                   X25519-Schlüssel (SecretBox)
                   und das lokale Profil
```

### 1. Aus dem Passwort werden zwei Schlüssel

Beim Registrieren und bei jedem Login berechnet die App mit **Argon2id** aus dem Passwort und einem zufälligen Salt 64 Byte (Parameter: `OPSLIMIT_MODERATE`, `MEMLIMIT_INTERACTIVE` = 64 MiB). Diese werden in zwei Hälften geteilt:

| Schlüssel | Verwendung | Verlässt das Gerät? |
|---|---|---|
| **Auth-Schlüssel** (Byte 0 bis 31) | Anmeldung am Server | Ja, aber der Server speichert davon nur einen **scrypt-Hash** mit eigenem Salt |
| **Tresor-Schlüssel** (Byte 32 bis 63) | Entschlüsselt den privaten Schlüssel und das lokale Profil | **Nein, niemals** |

Das Passwort selbst wird nie übertragen. Aus dem Auth-Schlüssel lässt sich der Tresor-Schlüssel nicht berechnen.

### 2. Jeder Nutzer hat ein Schlüsselpaar

Bei der Registrierung erzeugt die App ein **X25519-Schlüsselpaar**:

- Der **öffentliche Schlüssel** liegt offen auf dem Server, damit andere Nutzer dir schreiben können.
- Der **private Schlüssel** wird mit dem Tresor-Schlüssel per **SecretBox** (XSalsa20-Poly1305) verschlüsselt und nur in dieser Form auf dem Server abgelegt.

Dadurch kannst du dich auf jedem neuen Gerät anmelden: Die App lädt den verschlüsselten privaten Schlüssel herunter und entschlüsselt ihn lokal mit deinem Passwort. Der Server selbst kann damit nichts anfangen.

### 3. Nachrichten werden mit NaCl Box verschlüsselt

Jede Nachricht wird mit **`crypto_box`** verschlüsselt:

- **X25519** für den Schlüsselaustausch zwischen deinem privaten und dem öffentlichen Schlüssel des Empfängers
- **XSalsa20** für die eigentliche Verschlüsselung
- **Poly1305** als Prüfsumme, damit niemand die Nachricht unbemerkt verändern kann
- Eine **zufällige Nonce (24 Byte)** pro Nachricht

Format auf dem Draht: `Nonce (24 Byte) ‖ Chiffretext ‖ MAC (16 Byte)`, Base64-codiert. Desktop- und Android-App sind byte-genau kompatibel.

### 4. Die Transportverbindung ist zusätzlich TLS-geschützt

Die Verbindung zum Server läuft als **WebSocket über TLS**. Weil der Server ein selbstsigniertes Zertifikat nutzt, verwendet Herbstchat **Zertifikat-Pinning nach dem Trust-On-First-Use-Prinzip**:

1. Beim ersten Verbinden wird der SHA-256-Fingerabdruck des Zertifikats angezeigt.
2. Nach deiner Bestätigung merkt sich die App diesen Fingerabdruck.
3. Ändert er sich später, **bricht die App mit einer deutlichen Warnung ab**, statt einfach weiterzumachen.

Die Pins lassen sich in den Optionen zurücksetzen, falls das Zertifikat absichtlich erneuert wurde.

### 5. Kontakte prüfen: Sicherheitsnummer

Damit niemand dir einen falschen öffentlichen Schlüssel unterschieben kann (etwa ein manipulierter Server), gibt es die **Sicherheitsnummer**:

- Sie wird aus den beiden öffentlichen Schlüsseln berechnet (sortiert, SHA-256) und als 30 Ziffern in 6 Blöcken angezeigt.
- Beide Seiten sehen **dieselbe Nummer**. Vergleicht sie persönlich oder am Telefon.
- Stimmt sie überein, sprichst du wirklich mit der richtigen Person.

Zusätzlich zeigt **„Mein Schlüssel-Fingerabdruck“** einen kurzen Fingerabdruck deines eigenen öffentlichen Schlüssels. Der Desktop-Client merkt sich die Schlüssel deiner Kontakte und **warnt im Chat**, wenn sich einer ändert.

<!-- SCREENSHOT: Dialog Sicherheitsnummer (docs/screenshots/sicherheitsnummer.png) -->

### 6. Lokale Daten sind ebenfalls verschlüsselt

- **Desktop:** Verlauf, bekannte Kontaktschlüssel und ungelesene Nachrichten liegen in einem Profil, das mit dem Tresor-Schlüssel (SecretBox) verschlüsselt ist.
- **Android:** Das Profil ist ebenso verschlüsselt. Die Anmeldesitzung für den automatischen Login wird mit einem Schlüssel aus dem **Android-Keystore** gesichert. Dieser Schlüssel ist hardwaregestützt und kann nicht exportiert werden.

---

## Was der Server weiß und was nicht

Ehrlich gesagt: Ende-zu-Ende-Verschlüsselung schützt die **Inhalte**, aber nicht alle **Metadaten**. Das ist bei Herbstchat so:

| Der Server sieht … | Der Server sieht **nicht** … |
|---|---|
| Nickname, E-Mail-Adresse, Zeitpunkt der Registrierung | dein Passwort |
| letzten Login und letzte IP-Adresse | deinen Tresor-Schlüssel |
| deinen öffentlichen Schlüssel | deinen privaten Schlüssel (nur verschlüsselt) |
| deine Kontaktliste | den Inhalt deiner Nachrichten |
| wer wann wem eine Nachricht schickt und wie groß sie ist | den Inhalt deines Chatverlaufs |
| deinen Online-Status | dein lokales Profil |

Wer den Server betreibt, sollte das wissen und den Nutzern gegenüber offen damit umgehen.

---

## Chatverlauf auf mehreren Geräten

Ab Version **1.1.2** wird der Verlauf zwischen allen Geräten eines Kontos abgeglichen, zum Beispiel zwischen PC und Handy.

So funktioniert es:

1. Wenn du eine Nachricht schickst, legt der Server **zwei verschlüsselte Einträge** an: einen eingehenden beim Empfänger und einen ausgehenden bei dir. Beide enthalten nur den Chiffretext, den der Server ohnehin weiterleitet.
2. Jeder Eintrag bekommt eine fortlaufende Nummer pro Benutzer. Jedes Gerät merkt sich, bis zu welcher Nummer es schon alles hat.
3. Beim Login fragt das Gerät nur die **neuen Einträge** ab, seitenweise (bis 500 Einträge oder 512 KB pro Antwort).
4. Die App entschlüsselt lokal und führt den Verlauf zusammen. Doppelte Einträge werden über eine eindeutige Nachrichten-ID erkannt und aussortiert.
5. Bist du auf mehreren Geräten gleichzeitig online, bekommen die anderen Geräte sofort eine **Kopie deiner gesendeten Nachricht**.
6. **„Verlauf löschen“** löscht den Verlauf mit diesem Kontakt auf dem Gerät **und** auf dem Server, also auch für deine anderen Geräte.

Ältere Verläufe aus Version 1.0 bzw. 1.1.0 lädt jede App beim ersten Start mit 1.1.2 **einmalig** hoch, damit sie auch auf den anderen Geräten auftauchen.

Pro Benutzer speichert der Server höchstens **20 000** Verlaufseinträge. Ältere Einträge werden automatisch entfernt.

---

## Der Server

Der Server ist ein einzelnes Python-Programm (`server/herbstchat_server.py`) auf Basis von **aiohttp** und **SQLite**. Er braucht wenig Ressourcen und läuft problemlos auf einem Raspberry Pi.

### Ports

| Port | Protokoll | Zweck | Im Router freigeben? |
|---|---|---|---|
| **47474** | TCP, TLS, WebSocket (`/ws`) | Chat-Verbindung der Apps | **Ja** |
| **8088** | HTTP | Admin-Oberfläche | **Nein, niemals** |

### Wichtige Dateien

| Pfad | Inhalt |
|---|---|
| `/etc/herbstchat/server.conf` | Konfiguration (Ports, Zertifikat, Datenbank, Admin, SMTP) |
| `/etc/herbstchat/cert.pem`, `key.pem` | selbstsigniertes TLS-Zertifikat |
| `/etc/herbstchat/zertifikat-fingerabdruck.txt` | Fingerabdruck zum Vergleichen in den Apps |
| `/etc/herbstchat/admin-zugang.txt` | bei der Installation erzeugtes Admin-Passwort |
| `/var/lib/herbstchat/herbstchat.db` | SQLite-Datenbank (Benutzer, Kontakte, Warteschlange, Verlauf) |

### Konfiguration (Auszug)

```ini
[server]
host = 0.0.0.0
port = 47474
public_address = chat.example.org

[admin]
port = 8088
# Nur diese Netze dürfen auf die Admin-Oberfläche zugreifen
allowed_networks = 127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fe80::/10,fc00::/7

[smtp]
# Für Rundmails. Leer lassen = deaktiviert.
host =
port = 587
```

Nach Änderungen: `sudo systemctl restart herbstchat-server`

### Nützliche Befehle

```bash
sudo systemctl status herbstchat-server      # Status
sudo journalctl -u herbstchat-server -f      # Log live ansehen
sudo herbstchat-server --set-admin-password  # Admin-Passwort ändern
herbstchat-server --version                  # Version anzeigen
```

### Limits

| Grenze | Wert |
|---|---|
| maximale Größe einer verschlüsselten Nachricht | 64 KB |
| maximale Offline-Nachrichten pro Empfänger | 2 000 |
| Offline-Nachrichten verfallen nach | 60 Tagen |
| maximale Verlaufseinträge pro Benutzer | 20 000 |
| Nickname | 3 bis 24 Zeichen: Buchstaben, Zahlen, `_ - .` |

### Datenschutz-Details im Server

- Auth-Schlüssel und Admin-Passwort werden mit **scrypt** und eigenem Salt gespeichert und in konstanter Zeit verglichen.
- Für unbekannte Nicknamen liefert der Server beim Login ein **gleichbleibendes Schein-Salt**. Von außen lässt sich also nicht herausfinden, welche Nicknamen existieren.
- Nach **10 fehlgeschlagenen Logins innerhalb von 10 Minuten** wird die IP-Adresse gesperrt, bis die Fehlversuche älter als 10 Minuten sind.
- Offline-Nachrichten werden gelöscht, sobald der Empfänger sie bestätigt hat.

---

## Die Admin-Oberfläche

Erreichbar unter `http://<server-ip>:8088` **nur aus dem lokalen Netz**. Zugangsdaten stehen in `/etc/herbstchat/admin-zugang.txt`. Alle Formulare sind mit CSRF-Token geschützt.

| Bereich | Was man dort machen kann |
|---|---|
| **Dashboard** | Kennzahlen (Benutzer, online, aktiv in 24 h, neu in 7 Tagen, gebannt, Timeout, Offline-Nachrichten, Verlaufseinträge, Uptime, DB-Größe), letzte Ereignisse, Serveradresse |
| **Benutzer** | Suche und Filter (gebannt, Timeout, online, inaktiv), CSV-Export, Detailseite pro Benutzer |
| **Benutzer-Details** | Nickname/E-Mail ändern, Timeout, Bann, Stummschalten, Verbindung trennen, Systemnachricht (optional per E-Mail), interne Notiz, Offline-Nachrichten verwerfen, Sync-Verlauf löschen, Account löschen |
| **Rundschreiben** | Nachricht an alle in der App und/oder per E-Mail, gebannte Nutzer optional ausschließen |
| **Einstellungen** | Nachricht des Tages, Registrierung öffnen/schließen, Datenbank aufräumen (VACUUM) |
| **Protokoll** | Audit-Log aller wichtigen Aktionen |
| **Debug** | technische Übersicht, unter anderem zum Sync-Verlauf |

Auch in der Admin-Oberfläche sind **keine Nachrichteninhalte** sichtbar, nur Metadaten.

<!-- SCREENSHOT: Admin-Dashboard (docs/screenshots/admin-dashboard.png) -->
<!-- SCREENSHOT: Admin-Benutzerdetails (docs/screenshots/admin-benutzer.png) -->

---

## Desktop-Client

Geschrieben in **Python mit PySide6 (Qt 6)** und **PyNaCl**. Die Release-Dateien sind mit PyInstaller gebaut und brauchen kein installiertes Python.

### Menüs und Tastenkürzel

| Funktion | Kürzel |
|---|---|
| Optionen | Strg+, |
| Kontakt hinzufügen | Strg+N |
| Info über Herbstchat | F1 |
| Beenden | Strg+Q |

Weitere Menüpunkte: Passwort ändern, E-Mail-Adresse ändern, Mein Schlüssel-Fingerabdruck, Kontakt entfernen, Sicherheitsnummer prüfen, Verlauf mit Kontakt löschen, Status setzen, Abmelden.

### Optionen

- **Darstellung:** helles/dunkles Design, Akzentfarbe, Schriftart und -größe, Zeitstempel, kompakte Ansicht
- **Verhalten:** Enter sendet, Tipp-Anzeige senden, Verlauf speichern, offline Kontakte anzeigen, Start-Status
- **Töne:** neue Nachricht, gesendet, Kontakt kommt online, Lautstärke, stumm bei „Beschäftigt“
- **Benachrichtigungen:** Systembenachrichtigung, Vorschau des Textes, Taskleiste blinken
- **System:** Tray-Symbol, minimiert starten
- **Verbindung:** Server, Port, Zertifikats-Pins zurücksetzen

### Lokale Daten

| System | Ordner |
|---|---|
| Windows | `%LOCALAPPDATA%\Herbstchat` |
| macOS | `~/Library/Application Support/Herbstchat` |
| Linux | `~/.local/share/Herbstchat` |

<!-- SCREENSHOT: Optionen-Dialog (docs/screenshots/optionen.png) -->

---

## Android-App

Native App in **Kotlin mit Jetpack Compose**, ab **Android 8.0** (API 26). Sie nutzt **lazysodium** (libsodium) und ist kryptografisch voll kompatibel mit dem Desktop-Client.

- **Hintergrunddienst:** Ein Vordergrund-Dienst hält die Verbindung, damit Nachrichten sofort ankommen. Nach einem Neustart des Handys startet er automatisch.
- **Automatischer Login:** Die Sitzung ist über den Android-Keystore abgesichert.
- **Benachrichtigungen** für neue Nachrichten.
- **Gleiche Sicherheitsfunktionen:** Zertifikat-Pinning, Sicherheitsnummer, Schlüssel-Fingerabdruck.

> **Tipp:** In den Android-Einstellungen die **Akku-Optimierung für Herbstchat ausschalten**, sonst kann das System den Dienst im Hintergrund beenden.

<!-- SCREENSHOT: Android Kontaktliste und Chat (docs/screenshots/android-chat.png) -->

---

## Projektstruktur

```
herbstchat/
├── server/
│   ├── herbstchat_server.py     # Chat-Server + Admin-Oberfläche
│   ├── test_server.py           # Selbsttest (Registrierung, Login, Nachrichten, Sync)
│   ├── build-deb.sh             # baut das Debian-Paket
│   └── debian/                  # Paketdateien (control, postinst, systemd-Unit, server.conf …)
├── client/
│   ├── herbstchat.py            # Desktop-Client (PySide6 + PyNaCl)
│   ├── build.py                 # PyInstaller-Build für das aktuelle System
│   ├── requirements.txt
│   ├── start-linux.sh / start-macos.command / start-windows.bat
│   └── herbstchat.desktop       # Startmenü-Eintrag für Linux
├── android/                     # Android-App (Kotlin, Jetpack Compose)
│   └── app/src/main/java/org/herbstleyd/herbstchat/
│       ├── Crypto.kt            # Argon2id, SecretBox, Box, Sicherheitsnummer
│       ├── Connection.kt        # WebSocket über TLS mit Zertifikat-Pinning
│       ├── ChatCore.kt          # Protokoll und App-Zustand
│       ├── ChatService.kt       # Vordergrund-Dienst
│       ├── Store.kt             # Einstellungen, Pins, Sitzung, Profil
│       └── Ui.kt                # Oberfläche
├── .github/workflows/build-clients.yml   # CI: Tests, Builds, Release
├── INSTALLATION.md
└── README.md
```

---

## Selbst bauen

### Server-Paket

```bash
sudo apt install git dpkg-dev python3 python3-aiohttp python3-nacl openssl
git clone https://github.com/herbstleyd/herbstchat.git
cd herbstchat/server
python3 test_server.py     # Selbsttest
./build-deb.sh             # erzeugt herbstchat-server_<VERSION>_all.deb
```

### Desktop-Client

```bash
cd client
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python herbstchat.py       # direkt starten
python build.py            # eigenständige App in dist/ bauen
```

Alternativ starten die Skripte `start-linux.sh`, `start-macos.command` und `start-windows.bat` den Client direkt aus dem Quellcode.

### Android-App

```bash
cd android
./gradlew assembleRelease
```

Benötigt JDK 17 (wie im CI: Temurin 17) und das Android SDK.

### Automatische Releases

Bei jedem Push baut GitHub Actions Server-Paket, Windows-, macOS-, Linux- und Android-Version und testet sie. Wird ein Tag `vX.Y.Z` gepusht, prüft der Workflow, ob alle Versionsnummern zum Tag passen, und legt automatisch einen Release mit allen Dateien an:

```bash
git tag v1.2.0
git push origin v1.2.0
```

---

## Grenzen und Hinweise

Herbstchat ist ein privates Hobbyprojekt und **nicht von Dritten geprüft**. Bekannte Grenzen:

- **Keine Forward Secrecy:** Nachrichten werden mit den langlebigen Schlüsseln verschlüsselt (kein Double-Ratchet wie bei Signal). Wer an deinen privaten Schlüssel **und** an gespeicherte Chiffretexte kommt, kann diese entschlüsseln.
- **Das Passwort ist alles:** Es schützt den privaten Schlüssel. **Vergessene Passwörter lassen sich nicht wiederherstellen**, auch nicht vom Administrator. Ein neues Konto ist dann nötig.
- **Metadaten** (wer mit wem, wann) sind für den Server sichtbar, siehe oben.
- **Nur Textnachrichten**, keine Gruppen und keine Dateien.
- **Selbstsigniertes Zertifikat:** Die Sicherheit hängt davon ab, dass der Fingerabdruck beim ersten Verbinden wirklich geprüft wird.

---

## Häufige Fragen

**Kann der Admin meine Nachrichten lesen?**
Nein. Auf dem Server liegen nur verschlüsselte Daten. Der Schlüssel zum Entschlüsseln ist durch dein Passwort geschützt und verlässt dein Gerät nicht.

**Die App meldet „Das Server-Zertifikat hat sich geändert!“. Was nun?**
Nicht einfach weitermachen. Beim Betreiber nachfragen, ob das Zertifikat erneuert wurde, und den neuen Fingerabdruck vergleichen. Erst dann in den Optionen die Pins zurücksetzen.

**Im Chat steht „Der Schlüssel dieses Kontakts hat sich geändert“.**
Das passiert, wenn ein Kontakt ein neues Konto gleichen Namens hat oder etwas manipuliert wurde. Am besten die Sicherheitsnummer neu vergleichen.

**Auf dem Handy kommen Nachrichten verspätet an.**
Akku-Optimierung für Herbstchat ausschalten und prüfen, ob die dauerhafte Benachrichtigung des Dienstes sichtbar ist.

**Nach dem Update kann ich mich nicht mehr anmelden.**
Server und App müssen dieselbe Version haben. Bitte alles auf den neuesten Release bringen.

---

<div align="center">

Gemacht mit 🍂 von **Herbstleyd** · [herbstleyd.org](https://herbstleyd.org)

</div>
