# Herbstchat 1.1.0 – Installationsanleitung

Herbstchat ist ein privater Instant Messenger mit Ende-zu-Ende-Verschlüsselung, Offline-Nachrichten und einer Admin-Website, die nur im lokalen Netz erreichbar ist.

## Überblick

| Komponente | Datei | Plattform |
|---|---|---|
| Server | `herbstchat-server_1.1.0_all.deb` | Debian Testing, arm64 und amd64 (x86_64) |
| Client | Ordner `client/` | Windows 10/11, macOS 11+, alle Linux-Distributionen |
| Android-App | `Herbstchat-1.1.0.apk` (Quellcode in `android/`) | Android 8.0 oder neuer (arm64, armv7, x86, x86_64) |

### Ports

| Port | Protokoll | Zweck | Router-Weiterleitung |
|---|---|---|---|
| **47474** | TCP (TLS/WebSocket) | Chat-Verbindung der Clients | **JA**, an den Server weiterleiten |
| **8088** | TCP (HTTP) | Admin-Website | **NEIN**, auf keinen Fall weiterleiten |

Warum 47474? Der Port liegt im freien Bereich unter den flüchtigen Ports (49152+), ist bei der IANA nicht belegt und wird von keinem verbreiteten Dienst genutzt. Außerdem kann man ihn sich leicht merken.

Clients verbinden sich mit **chat.example.org : 47474**. Diese Adresse ist im Client schon voreingestellt.

## Sicherheitskonzept

- **Ende-zu-Ende-Verschlüsselung:** Jeder Benutzer erzeugt bei der Registrierung auf seinem eigenen Gerät ein X25519-Schlüsselpaar. Nachrichten werden mit NaCl/libsodium `crypto_box` (X25519 + XSalsa20-Poly1305) verschlüsselt, bevor sie das Gerät verlassen.
- **Das Passwort verlässt nie das Gerät.** Der Client leitet daraus per Argon2id zwei Schlüssel ab:
  - einen Auth-Schlüssel, der an den Server geht. Der Server speichert davon nur einen scrypt-Hash.
  - einen Tresor-Schlüssel, der lokal bleibt. Mit ihm ist der private Schlüssel verschlüsselt, bevor er auf dem Server gesichert wird. Deshalb kann man sich auf jedem PC einloggen.
- **Auch du als Betreiber kannst nichts lesen.** In der Datenbank liegen nur Chiffretext, öffentliche Schlüssel und verschlüsselte private Schlüssel.
- **Offline-Nachrichten** bleiben verschlüsselt auf dem Server, bis der Empfänger online kommt. Sobald er den Empfang bestätigt, werden sie **gelöscht**. Nicht zugestellte Nachrichten verfallen nach 60 Tagen.
- **Transportverschlüsselung:** Bei der Installation wird ein TLS-Zertifikat erzeugt. Beim ersten Verbinden zeigt der Client den Fingerabdruck an und merkt ihn sich (Pinning). Ändert sich das Zertifikat später, warnt der Client.
- **Sicherheitsnummer:** Über „Kontakte → Sicherheitsnummer prüfen“ können zwei Benutzer vergleichen, ob ihre Schlüssel echt sind. Damit ist auch ein manipulierter Server ausgeschlossen.
- **Folge:** Ein vergessenes Passwort kann niemand zurücksetzen, auch der Admin nicht. In diesem Fall muss der Benutzer einen neuen Account anlegen.

## Teil 1: Server installieren (Debian Testing, ARM64 oder x86_64)

### 1.1 Voraussetzungen

```bash
sudo apt update
sudo apt install python3 python3-aiohttp openssl
```

(`apt` installiert diese Abhängigkeiten im nächsten Schritt auch automatisch.)

### 1.2 Paket installieren

`herbstchat-server_1.1.0_all.deb` auf den Server kopieren, zum Beispiel mit `scp`:

```bash
scp herbstchat-server_1.1.0_all.deb benutzer@<server-lan-ip>:~
```

Auf dem Server:

```bash
sudo apt install ./herbstchat-server_1.1.0_all.deb
```

Das Paket ist `Architecture: all` (reines Python) und läuft deshalb auf **arm64 und amd64** gleichermaßen.

Bei der Installation passiert automatisch:

1. Der Systembenutzer `herbstchat` wird angelegt (ohne Login, ohne Shell).
2. Das Datenverzeichnis `/var/lib/herbstchat/` wird angelegt (SQLite-Datenbank).
3. Ein TLS-Zertifikat für `chat.example.org` wird erzeugt (ECDSA P-256, 10 Jahre gültig).
4. Ein **zufälliges Admin-Passwort** wird erzeugt und angezeigt. Es steht außerdem in `/etc/herbstchat/admin-zugang.txt`.
5. Der systemd-Dienst `herbstchat-server` wird aktiviert und gestartet.

Admin-Zugang nachträglich anzeigen:

```bash
sudo cat /etc/herbstchat/admin-zugang.txt
```

Zertifikat-Fingerabdruck anzeigen (zum Vergleichen beim ersten Client-Start):

```bash
cat /etc/herbstchat/zertifikat-fingerabdruck.txt
```

### 1.3 Dienst prüfen

```bash
systemctl status herbstchat-server
journalctl -u herbstchat-server -f        # Live-Log
ss -ltnp | grep -E '47474|8088'           # lauscht der Server?
```

Test aus dem LAN:

```bash
curl -k https://<server-lan-ip>:47474/    # Antwort: "Herbstchat Server 1.1.0"
```

### 1.4 Router / Portweiterleitung

Im Router (zum Beispiel FritzBox unter „Internet → Freigaben → Portfreigaben“):

- **TCP 47474 → <Server-LAN-IP>:47474** freigeben
- Port **8088 NICHT** freigeben

Prüfe außerdem, ob `chat.example.org` auf deine aktuelle öffentliche IP zeigt (DynDNS-Client im Router oder auf dem Server). Bei IPv6-only- oder DS-Lite-Anschlüssen muss die Freigabe für IPv6 eingerichtet werden.

### 1.5 Optionale Firewall (nftables / ufw)

Mit ufw:

```bash
sudo apt install ufw
sudo ufw allow 22/tcp                          # SSH nicht aussperren
sudo ufw allow 47474/tcp                       # Chat
sudo ufw allow from 192.168.0.0/16 to any port 8088 proto tcp   # Admin nur aus dem LAN
sudo ufw enable
```

(Passe `192.168.0.0/16` an dein Heimnetz an, zum Beispiel `192.168.178.0/24` bei einer FritzBox.)

Zusätzlich lehnt die Admin-Website **jede Anfrage aus nicht-privaten Netzen** mit HTTP 403 ab. Erlaubt sind nur Adressen aus `allowed_networks` in der Konfiguration. Selbst bei einer versehentlichen Weiterleitung ist die Seite also von außen nicht nutzbar.

### 1.6 Konfiguration

Datei: `/etc/herbstchat/server.conf`

```ini
[server]
port = 47474                 # Chat-Port
public_address = chat.example.org

[admin]
port = 8088                  # Admin-Website (nur LAN)
user = admin
allowed_networks = 127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,...

[smtp]                       # für Wartungs-E-Mails an alle Benutzer
host = smtp.example.org
port = 587
user = herbstchat@example.org
password = ...
sender = Herbstchat <herbstchat@example.org>
starttls = yes
```

Nach Änderungen:

```bash
sudo systemctl restart herbstchat-server
```

Admin-Passwort ändern:

```bash
sudo herbstchat-server --set-admin-password
sudo systemctl restart herbstchat-server
```

### 1.7 Optional: richtiges Let's-Encrypt-Zertifikat

Das selbst erzeugte Zertifikat ist sicher, weil die Clients es pinnen. Wer lieber ein offizielles Zertifikat nutzt:

```bash
sudo apt install certbot
sudo certbot certonly --standalone -d chat.example.org   # Port 80 muss dafür kurz weitergeleitet sein
sudo cp /etc/letsencrypt/live/chat.example.org/fullchain.pem /etc/herbstchat/cert.pem
sudo cp /etc/letsencrypt/live/chat.example.org/privkey.pem  /etc/herbstchat/key.pem
sudo chown root:herbstchat /etc/herbstchat/*.pem && sudo chmod 640 /etc/herbstchat/key.pem
sudo systemctl restart herbstchat-server
```

Wichtig: Nach einem Zertifikatswechsel warnen bestehende Clients. Dort einmal „Optionen → System → Server-Vertrauen zurücksetzen“ klicken.

### 1.8 Backup

```bash
sudo systemctl stop herbstchat-server
sudo tar czf herbstchat-backup-$(date +%F).tar.gz /var/lib/herbstchat /etc/herbstchat
sudo systemctl start herbstchat-server
```

### 1.9 Update / Deinstallation

```bash
sudo apt install ./herbstchat-server_<neue-version>_all.deb   # Update, Daten bleiben erhalten
sudo apt remove herbstchat-server                              # entfernen, Daten bleiben erhalten
sudo apt purge herbstchat-server                               # ALLES löschen inkl. Datenbank
```

## Teil 2: Admin-Website

Im Browser **aus dem lokalen Netz** öffnen:

```
http://<Server-LAN-IP>:8088
```

Anmeldung mit `admin` und dem Passwort aus `/etc/herbstchat/admin-zugang.txt`.

### Funktionen

**Dashboard**
- Benutzer gesamt, online, aktiv in den letzten 24 h, neu in den letzten 7 Tagen
- Anzahl gebannter Accounts, Accounts im Timeout, wartende Offline-Nachrichten
- Uptime, Größe der Datenbank, letzte Ereignisse

**Benutzerliste**
- Suche nach Nickname oder E-Mail
- Filter: online, gebannt, im Timeout, inaktiv seit über 90 Tagen
- Sortierung nach Nick, Registrierung, letztem Login oder Anzahl der Nachrichten
- Export aller E-Mail-Adressen als CSV

**Benutzerdetails und Aktionen**
- E-Mail, Registrierung, letzter Login mit IP-Adresse, Zahl der Nachrichten und Kontakte, Schlüssel-Fingerabdruck
- **Nickname ändern** (die Kontakte des Benutzers sehen den neuen Namen sofort)
- **E-Mail ändern**
- **Timeout** für 6 h, 12 h, 1, 2, 3, 7, 14 oder 30 Tage, mit Grund. Der Benutzer wird sofort getrennt und kann sich bis zum Ablauf nicht anmelden.
- **Bannen / Entbannen** mit Grund
- **Stummschalten:** Der Benutzer kann sich anmelden und lesen, aber nichts senden.
- **Verbindung trennen** (Kick)
- **Systemnachricht** an einen einzelnen Benutzer, auf Wunsch zusätzlich per E-Mail
- **Admin-Notiz** (nur intern sichtbar)
- **Offline-Nachrichten verwerfen**
- **Account löschen**

**Rundschreiben**
- Wartungsankündigung als Pop-up an alle Benutzer, die gerade online sind, und/oder per E-Mail an alle

**Einstellungen**
- Nachricht des Tages (erscheint beim Login)
- Neue Registrierungen sperren und wieder freigeben
- Test-E-Mail senden
- Datenbank optimieren (VACUUM)

**Protokoll**
- Registrierungen, Admin-Aktionen und Passwortänderungen

Nachrichteninhalte kann auch die Admin-Website **nicht** anzeigen. Das ist gewollt.

## Teil 3: Client installieren

Der Client ist ein grafisches Programm (Qt / PySide6) und läuft auf Windows, macOS und Linux.

### Variante A: Startskript (am einfachsten, für alle Systeme)

Voraussetzung ist **Python 3.9 oder neuer**.

**Windows 10/11**
1. Python von [python.org](https://www.python.org/downloads/) installieren. Dabei **„Add python.exe to PATH“** anhaken.
2. Den Ordner `client` entpacken, zum Beispiel nach `C:\Herbstchat`.
3. Doppelklick auf **`start-windows.bat`**. Beim ersten Start werden die Pakete geladen, das dauert 1–2 Minuten.

**macOS**
1. Python 3 installieren (von [python.org](https://www.python.org/downloads/) oder mit `brew install python`).
2. Den Ordner `client` entpacken.
3. Im Terminal einmal `chmod +x start-macos.command` ausführen. Danach reicht ein Doppelklick auf **`start-macos.command`**.

**Linux (Debian/Ubuntu/Mint/Raspberry Pi OS, Fedora, Arch, openSUSE …)**

```bash
# Debian/Ubuntu:  sudo apt install python3 python3-venv libxcb-cursor0
# Fedora:         sudo dnf install python3 xcb-util-cursor
# Arch:           sudo pacman -S python xcb-util-cursor
cd ~/Herbstchat        # entpackter Ordner "client"
./start-linux.sh
```

Optional einen Startmenü-Eintrag anlegen:

```bash
cp herbstchat.desktop ~/.local/share/applications/
```

(Pfad in `Exec=` gegebenenfalls anpassen.)

### Variante B: eigenständige App bauen (ohne Python beim Benutzer)

Die App muss auf dem jeweiligen Betriebssystem gebaut werden:

```bash
cd client
python build.py
```

Ergebnis:
- Windows: `dist/Herbstchat.exe`
- macOS: `dist/Herbstchat.app`
- Linux: `dist/Herbstchat`

**Automatisch über GitHub:** Wenn du das Projekt in ein GitHub-Repository hochlädst, baut der mitgelieferte Workflow `.github/workflows/build-clients.yml` bei jedem Push alle drei Versionen. Du findest sie danach unter „Actions → Artifacts“. Der Linux-Build läuft auf Ubuntu 22.04 und funktioniert deshalb auch auf älteren Distributionen.

Hinweis für macOS: Die App ist nicht signiert. Beim ersten Öffnen musst du sie mit Rechtsklick → „Öffnen“ bestätigen.

## Teil 3b: Android-App

Die Android-App ist eine native App (Kotlin, Jetpack Compose). Sie nutzt dieselbe Verschlüsselung wie der Desktop-Client (libsodium: Argon2id, X25519, XSalsa20-Poly1305) und ist voll kompatibel: Ein Konto funktioniert auf PC und Handy, und Android- und Desktop-Nutzer können miteinander chatten.

### Installieren

1. `Herbstchat-1.1.0.apk` aufs Handy kopieren (USB, Cloud, E-Mail oder per Download).
2. Die Datei antippen. Android fragt beim ersten Mal, ob Apps aus dieser Quelle installiert werden dürfen. Erlauben, zurück und „Installieren“ antippen.
3. Herbstchat öffnen, Benachrichtigungen erlauben, anmelden oder registrieren.
4. Beim ersten Verbinden den Zertifikat-Fingerabdruck bestätigen, genau wie am PC.

Alternativ per ADB: `adb install Herbstchat-1.1.0.apk`

### Besonderheiten am Handy

- **Angemeldet bleiben:** Beim Anmelden ankreuzbar. Das Passwort wird nicht gespeichert. Gespeichert werden nur die daraus abgeleiteten Schlüssel, und die sind mit einem Hardware-Schlüssel aus dem Android-Keystore verschlüsselt. Nach einem Neustart meldet sich die App selbst wieder an.
- **Nachrichten im Hintergrund:** Die App hält über einen Vordergrund-Dienst die Verbindung offen. Dafür steht eine unauffällige, dauerhafte Benachrichtigung „Herbstchat – Verbunden als …“ in der Leiste. Abschaltbar unter Einstellungen → Hintergrund.
- **Akku-Optimierung:** Damit Nachrichten auch bei ausgeschaltetem Bildschirm sofort ankommen, unter Einstellungen → „Akku-Optimierung für Herbstchat abschalten“ tippen. Bei Xiaomi, Huawei, Samsung und ähnlichen zusätzlich in den Geräte-Einstellungen „Autostart“ bzw. „Keine Einschränkungen“ für Herbstchat setzen.
- **Ton und Vibration** stellst du in den Android-Benachrichtigungseinstellungen ein (Link in den App-Einstellungen). Im Status „Beschäftigt“ gibt es keine Benachrichtigungen.
- Der Chatverlauf liegt verschlüsselt im privaten App-Speicher und wird nicht in Android-Backups übernommen.

### Selbst bauen

```bash
cd android
./gradlew assembleRelease          # braucht JDK 17 und das Android SDK (ANDROID_HOME)
```

Ohne Signaturschlüssel wird mit dem Debug-Schlüssel signiert. Für Updates muss jede neue Version mit **demselben** Schlüssel signiert sein wie die installierte, sonst lehnt Android das Update ab. Den Release-Schlüssel (`herbstchat-release.jks`) daher gut aufbewahren:

```bash
export HC_KEYSTORE=/pfad/zu/herbstchat-release.jks
export HC_KEYSTORE_PASSWORD='…'
./gradlew assembleRelease          # Ergebnis: app/build/outputs/apk/release/app-release.apk
```

Der GitHub-Workflow baut die APK bei jedem Push automatisch mit (Artefakt „Herbstchat-Android“), sofern die Secrets `HC_KEYSTORE_B64` und `HC_KEYSTORE_PASSWORD` gesetzt sind.

## Teil 4: Erste Schritte für Benutzer

1. Herbstchat starten. Der Server `chat.example.org`, Port `47474`, ist schon eingetragen.
2. Im Reiter **„Registrieren“** E-Mail-Adresse, Nickname (3–24 Zeichen) und ein Passwort (**mindestens 6 Zeichen**) eingeben. Danach auf „Account erstellen“ klicken.
3. Beim ersten Verbinden erscheint der Zertifikat-Fingerabdruck. Mit „Ja“ bestätigen. Wer sichergehen will, vergleicht ihn vorher mit `/etc/herbstchat/zertifikat-fingerabdruck.txt`.
4. Über **„+ Kontakt hinzufügen“** nach einem Nickname suchen.
5. Chatten. Ist der Kontakt offline, wird die Nachricht zugestellt, sobald er sich anmeldet (Symbol ✉).

### Menüs im Client

- **Herbstchat:** Optionen, Passwort ändern, E-Mail ändern, eigener Schlüssel-Fingerabdruck, Abmelden, Beenden
- **Kontakte:** hinzufügen, entfernen, Sicherheitsnummer prüfen, Verlauf löschen
- **Status:** Online, Abwesend, Beschäftigt, Unsichtbar
- **Info:** Über Herbstchat (mit Link zu herbstleyd.org)

### Optionen (ähnlich wie bei ICQ)

- **Darstellung:** Schriftart, Schriftgröße (8–24 pt), helles oder dunkles Design, 6 Akzentfarben, Uhrzeit anzeigen, kompakte Ansicht, Offline-Kontakte ein- oder ausblenden
- **Töne:** an/aus, „Uh-oh“ bei neuer Nachricht, Ton beim Senden, Ton wenn ein Kontakt online kommt, Lautstärke, stumm im Status „Beschäftigt“, Ton testen
- **Benachrichtigungen:** Desktop-Benachrichtigung, Vorschau ein/aus, Taskleiste blinken lassen
- **Chat & Privatsphäre:** Enter sendet (Umschalt+Enter macht eine neue Zeile), Tipp-Anzeige senden, Verlauf lokal und verschlüsselt speichern, Verlauf löschen
- **System:** in den Tray minimieren, minimiert starten, Status beim Login, Server und Port, Server-Vertrauen zurücksetzen

Lokale Daten liegen hier (Chatverlauf verschlüsselt):
- Windows: `%LOCALAPPDATA%\Herbstchat`
- macOS: `~/Library/Application Support/Herbstchat`
- Linux: `~/.local/share/Herbstchat`

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| Client meldet „Verbindung fehlgeschlagen“ | Portweiterleitung 47474/TCP prüfen, `systemctl status herbstchat-server` ausführen, DynDNS-IP prüfen (`ping chat.example.org`) |
| Aus dem eigenen LAN klappt es nicht, von außen schon | Der Router unterstützt kein NAT-Loopback. Im Client als Server die LAN-IP eintragen und unter Optionen das Server-Vertrauen zurücksetzen. |
| „Zertifikat hat sich geändert“ | Nur nach Neuinstallation oder Zertifikatswechsel normal: Optionen → System → Server-Vertrauen zurücksetzen |
| Admin-Website zeigt 403 | Du greifst nicht aus einem erlaubten Netz zu. `allowed_networks` prüfen. |
| Linux-Client startet nicht (xcb-Fehler) | `sudo apt install libxcb-cursor0` |
| Passwort vergessen | Kann wegen der Ende-zu-Ende-Verschlüsselung nicht zurückgesetzt werden. Neuen Account anlegen, den alten löscht der Admin. |
| Android: Nachrichten kommen erst beim Öffnen der App | Akku-Optimierung für Herbstchat abschalten, „Im Hintergrund verbunden bleiben“ einschalten, bei manchen Herstellern Autostart erlauben |
| Android: „App nicht installiert“ beim Update | Die neue APK ist mit einem anderen Schlüssel signiert. Alte App deinstallieren oder mit dem ursprünglichen Schlüssel neu bauen. |
| E-Mails werden nicht versendet | `[smtp]` in `server.conf` ausfüllen, Dienst neu starten, Test-E-Mail über die Einstellungen senden |

## Dateien im Paket

```
/usr/bin/herbstchat-server                     Startbefehl
/usr/lib/herbstchat-server/herbstchat_server.py Server (Python, aiohttp)
/etc/herbstchat/server.conf                    Konfiguration
/etc/herbstchat/cert.pem, key.pem              TLS-Zertifikat
/etc/herbstchat/admin-zugang.txt               Admin-Zugangsdaten
/var/lib/herbstchat/herbstchat.db              SQLite-Datenbank
/lib/systemd/system/herbstchat-server.service  systemd-Dienst
```

Herbstchat – [herbstleyd.org](https://herbstleyd.org)
