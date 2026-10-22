# Herbstchat – Installationsanleitung

Herbstchat ist ein privater Instant Messenger mit Ende-zu-Ende-Verschlüsselung. Jede Nachricht wird vor dem Verlassen des jeweiligen Geräts mit einem asymmetrischen Verfahren (X25519 + XSalsa20-Poly1305) verschlüsselt. Der Server und sogar ein Administrator können die Nachrichteninhalte nicht lesen.

## 1. Server installieren

Der Server läuft als Python-Dienst (mit `aiohttp` & SQLite) und wird empfohlen unter Debian oder Ubuntu. Er wird über `systemd` verwaltet.

### 1.1 Debian-Paket installieren (empfohlen)

Lade `herbstchat-server_<VERSION>_all.deb` aus den GitHub-Releases herunter und installiere es:
```bash
sudo apt install ./herbstchat-server_*_all.deb
```
Das Paket legt Benutzer, Konfiguration (`/etc/herbstchat/server.conf`), TLS-Zertifikat, Admin-Passwort
(`/etc/herbstchat/admin-zugang.txt`) und den systemd-Dienst automatisch an und startet den Server.

### 1.2 Paket selbst aus dem Quellcode bauen

```bash
sudo apt install git dpkg-dev python3 python3-aiohttp openssl
git clone https://github.com/herbstleyd/herbstchat.git
cd herbstchat/server
python3 test_server.py        # optional: Selbsttest (braucht zusätzlich python3-nacl)
./build-deb.sh                # erzeugt herbstchat-server_<VERSION>_all.deb
sudo apt install ./herbstchat-server_*_all.deb
```

### 1.3 Zertifikat und Konfiguration

1. **TLS-Zertifikat:** Wird bei der Installation selbstsigniert erzeugt (`/etc/herbstchat/cert.pem`, Fingerabdruck in `/etc/herbstchat/zertifikat-fingerabdruck.txt`).
2. **Admin-Passwort ändern** (optional):
```bash
sudo herbstchat-server --set-admin-password
```

### 1.4 Dienst starten

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now herbstchat-server
sudo systemctl status herbstchat-server
```

**Hinweis zu Ports:**
- **Chat-Verkehr:** Port `47474` (TCP, TLS). Muss im Router nach außen freigegeben werden.
- **Admin-Oberfläche:** Port `8088` (HTTP). Darf *niemals* ins Internet geroutet werden, sie ist nur für das lokale Netz vorgesehen.

---

### 1.5 Client-Installation (Windows, macOS, Linux)

Die Desktop-Clients sind als einzelne Dateien kompiliert und benötigen keine lokalen Abhängigkeiten (wie Python oder Java).

#### Windows
1. Lade die `Herbstchat-Windows.exe` herunter.
2. Doppelklicke auf die Datei, um sie zu starten.
*(Optional: Erstelle auf dem Desktop einen Shortcut.)*

#### macOS
1. Lade die `Herbstchat-macOS.zip` herunter und entpacke sie.
2. Ziehe die App in den `Programme`-Ordner. 
3. Beim ersten Start erscheint eine Warnung, da die App nicht über den App Store stammt. Gehe in `Systemeinstellungen > Sicherheit und Datenschutz` und erlaube die Ausführung. Alternativ: Rechtsklick auf die App > "Öffnen".

#### Linux
1. Lade die `Herbstchat-Linux-x86_64` herunter.
2. Mache die Datei ausführbar und starte sie:
```bash
chmod +x Herbstchat-Linux-x86_64
./Herbstchat-Linux-x86_64
```
*(Optional: Kopiere die beigefügte `herbstchat.desktop` in `~/.local/share/applications/` und passe den `Exec=`-Pfad an, um einen Eintrag im Startmenü zu erhalten.)*

---

### 1.6 Android-App

Die Android-App (`Herbstchat-<VERSION>.apk`) ist eine native Kotlin-App und nutzt dieselbe E2EE-Technologie wie der Desktop-Client.

1. Lade die APK-Datei auf dein Smartphone.
2. Öffne die Datei und erlaube die Installation aus dieser Quelle.
3. *Tipp:* Schalte im Android-System die Akku-Optimierung für Herbstchat aus, damit Nachrichten auch im Hintergrund sofort zugestellt werden.

---

### 1.7 Erste Schritte & Konto-Setup

1. Starte Herbstchat auf deinem Endgerät.
2. Der Server ist standardmäßig auf `chat.example.org:47474` eingestellt. Passe dies an, falls du eine andere IP oder Domain nutzt.
3. Gib deine E-Mail, einen Namen (Nickname) und ein sicheres Passwort ein.
4. Beim ersten Verbinden siehst du den Zertifikats-Fingerabdruck des Servers. Vergleiche ihn ggf. mit `cat /etc/herbstchat/zertifikat-fingerabdruck.txt` und bestätige ihn.

---

### 1.8 Update und Deinstallation

**Update:**
- Server: Lade das neue `.deb` herunter und installiere es (`sudo apt install ./herbstchat-server_*.deb`). Deine Einstellungen und Chats bleiben erhalten.
- Clients: Ersetze die alte Binary einfach durch die neue Version.

**Deinstallation:**
- Server: `sudo apt purge herbstchat-server` (löscht Serverdaten! Erstelle vorher ein Backup von `/var/lib/herbstchat/`).
- Clients: Lösche die heruntergeladenen Programmdateien. Lokale Cache-Daten finden sich unter `%LOCALAPPDATA%\\Herbstchat` (Windows), `~/Library/Application Support/Herbstchat` (macOS) und `~/.local/share/Herbstchat` (Linux).

---

### 1.9 Chatverlauf auf mehreren Geräten

Ab Version 1.1.2 wird der Chatverlauf automatisch zwischen allen Geräten eines Kontos abgeglichen.
Der Server speichert dafür nur verschlüsselte Daten (max. 20 000 Einträge pro Benutzer); lesen kann er sie nicht.
„Verlauf löschen“ im Client löscht auch die Kopie auf dem Server. Server und Clients sollten dieselbe Version haben.
