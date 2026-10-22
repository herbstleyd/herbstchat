#!/usr/bin/env python3
"""Herbstchat Client - grafischer, Ende-zu-Ende-verschlüsselter Messenger.
Windows / macOS / Linux  (Python 3.9+, PySide6, PyNaCl)
"""
import base64, datetime, hashlib, html, json, math, os, struct, sys, time, uuid, wave

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QStandardPaths, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QPainter, QPixmap, QKeySequence,
                           QDesktopServices, QTextCursor, QBrush, QPen)
from PySide6.QtNetwork import QSslSocket, QSslError
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTabWidget, QFormLayout, QMessageBox, QListWidget,
                               QListWidgetItem, QSplitter, QTextBrowser, QPlainTextEdit, QComboBox, QSpinBox,
                               QCheckBox, QSlider, QFontComboBox, QSystemTrayIcon, QMenu, QInputDialog,
                               QDialogButtonBox, QGridLayout, QToolButton, QFrame, QSizePolicy)
import nacl.public, nacl.secret, nacl.utils, nacl.pwhash
from nacl.pwhash import argon2id

try:
    from PySide6.QtMultimedia import QSoundEffect
except Exception:  # pragma: no cover
    QSoundEffect = None

APP = "Herbstchat"
VERSION = "1.1.2"
DEFAULT_SERVER = ""          # eigene Serveradresse beim ersten Start eintragen
DEFAULT_PORT = 47474
WEBSITE = "https://herbstleyd.org"

DATA_DIR = os.path.join(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation) or
                        os.path.expanduser("~"), "Herbstchat")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PINS_FILE = os.path.join(DATA_DIR, "server_pins.json")

ACCENT_DEFAULT = "#0066cc"
ACCENTS = {"Herbstchat-Blau": "#0066cc", "Himmelblau": "#2f9bd8", "Petrol": "#00838f",
           "Waldgrün": "#3d8b4f", "Violett": "#6a4fc8", "Ahorn-Rot": "#c0392b"}
DEFAULTS = {
    "server": DEFAULT_SERVER, "port": DEFAULT_PORT, "last_nick": "", "remember_nick": True,
    "font_family": "", "font_size": 11, "theme": "dunkel", "accent": ACCENT_DEFAULT, "show_time": True,
    "enter_sends": True, "compact": False,
    "sound_on": True, "sound_msg": True, "sound_sent": False, "sound_online": True, "volume": 70,
    "sound_dnd_busy": True,
    "notify": True, "notify_preview": True, "flash_taskbar": True,
    "tray": True, "start_minimized": False, "send_typing": True, "save_history": True,
    "start_status": "online", "show_offline": True,
}
STATUS = {"online": ("Online", "#3bb54a"), "away": ("Abwesend", "#f1c40f"),
          "busy": ("Beschäftigt", "#e74c3c"), "invisible": ("Unsichtbar", "#95a5a6"),
          "offline": ("Offline", "#7f8c8d")}
EMOJIS = "😀 😂 😊 😍 😘 😎 🤔 😅 😢 😭 😡 👍 👎 👋 🙏 👏 💪 ❤️ 💔 🔥 🎉 🍂 🍁 ☕ 🍺 🎂 🌞 🌧️ ⭐ ✅ ❌ ❓".split()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


b64e = lambda b: base64.b64encode(b).decode()
b64d = base64.b64decode


def derive(password, salt):
    """Argon2id -> 32 Byte Auth-Schlüssel (an Server) + 32 Byte Tresor-Schlüssel (bleibt lokal)."""
    k = argon2id.kdf(64, password.encode("utf-8"), salt,
                     opslimit=argon2id.OPSLIMIT_MODERATE, memlimit=argon2id.MEMLIMIT_INTERACTIVE)
    return k[:32], k[32:]


def safety_number(a, b):
    h = hashlib.sha256(b"".join(sorted([b64d(a), b64d(b)]))).hexdigest()
    digits = str(int(h[:40], 16))[:30].rjust(30, "0")
    return " ".join(digits[i:i + 5] for i in range(0, 30, 5))


# --------------------------------------------------------------------------- Sounds / Icons
def make_sounds():
    def tone(name, notes):
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            return path
        rate, frames = 22050, bytearray()
        for freq, dur in notes:
            n = int(rate * dur)
            for i in range(n):
                env = min(1, i / 300) * min(1, (n - i) / 800)
                v = 0.45 * env * math.sin(2 * math.pi * freq * i / rate) if freq else 0
                frames += struct.pack("<h", int(v * 32767))
        with wave.open(path, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(bytes(frames))
        return path
    return {"msg": tone("msg.wav", [(880, .12), (0, .04), (660, .18)]),          # "Uh-oh" im ICQ-Stil
            "sent": tone("sent.wav", [(1200, .05)]),
            "online": tone("online.wav", [(523, .1), (659, .1), (784, .16)]),
            "notice": tone("notice.wav", [(440, .2), (0, .05), (440, .2)])}


def app_icon(color=ACCENT_DEFAULT):
    pm = QPixmap(64, 64); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color)); p.setPen(Qt.NoPen); p.drawRoundedRect(2, 2, 60, 60, 16, 16)
    p.setPen(QColor("white")); f = QFont(); f.setBold(True); f.setPixelSize(38); p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "H"); p.end()
    return QIcon(pm)


def dot_icon(color, unread=0):
    pm = QPixmap(28, 28); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color)); p.setPen(QPen(QColor("white"), 2)); p.drawEllipse(6, 6, 16, 16)
    if unread:
        p.setBrush(QColor("#e74c3c")); p.setPen(Qt.NoPen); p.drawEllipse(14, 0, 14, 14)
        p.setPen(QColor("white")); f = QFont(); f.setPixelSize(9); f.setBold(True); p.setFont(f)
        p.drawText(14, 0, 14, 14, Qt.AlignCenter, str(min(unread, 99)))
    p.end()
    return QIcon(pm)


def stylesheet(s):
    dark = s["theme"] == "dunkel"
    a = s["accent"]
    bg, panel, text, border, inp = (("#16191e", "#1f242b", "#e6e9ee", "#2f3640", "#262c34") if dark else
                                    ("#eef2f7", "#ffffff", "#1c2430", "#d5dde8", "#ffffff"))
    fam = f"font-family:'{s['font_family']}';" if s["font_family"] else ""
    return f"""
    * {{ {fam} font-size:{s['font_size']}pt; color:{text}; }}
    QMainWindow, QDialog {{ background:{bg}; }}
    QWidget#panel {{ background:{panel}; border-radius:12px; }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QTextBrowser, QListWidget, QFontComboBox {{
        background:{inp}; border:1px solid {border}; border-radius:8px; padding:6px; selection-background-color:{a}; }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border:1px solid {a}; }}
    QPushButton {{ background:{a}; color:white; border:none; border-radius:8px; padding:8px 16px; font-weight:600; }}
    QPushButton:hover {{ background:{QColor(a).lighter(115).name()}; }}
    QPushButton:disabled {{ background:#999; }}
    QPushButton[flat="true"], QToolButton {{ background:transparent; color:{text}; border:1px solid {border}; border-radius:8px; padding:5px 9px; }}
    QListWidget::item {{ padding:8px; border-radius:8px; }}
    QListWidget::item:selected {{ background:{a}; color:white; }}
    QListWidget::item:hover:!selected {{ background:{QColor(a).lighter(185).name() if not dark else '#2a323d'}; }}
    QTabWidget::pane {{ border:1px solid {border}; border-radius:8px; background:{panel}; }}
    QTabBar::tab {{ padding:8px 14px; background:transparent; }}
    QTabBar::tab:selected {{ border-bottom:3px solid {a}; font-weight:600; }}
    QMenuBar {{ background:{panel}; }} QMenuBar::item:selected, QMenu::item:selected {{ background:{a}; color:white; }}
    QMenu {{ background:{panel}; border:1px solid {border}; }}
    QLabel#title {{ font-size:{s['font_size']+9}pt; font-weight:700; color:{a}; }}
    QLabel#chathead {{ font-size:{s['font_size']+3}pt; font-weight:700; }}
    QLabel#muted {{ color:#888; }}
    """


# --------------------------------------------------------------------------- Connection
class Connection(QWebSocket):
    message = Signal(dict)
    state = Signal(str)

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.textMessageReceived.connect(self._rx)
        self.connected.connect(lambda: self.state.emit("connected"))
        self.disconnected.connect(lambda: self.state.emit("disconnected"))
        self.sslErrors.connect(self._ssl)
        self.host, self.port = "", 0

    def open_to(self, host, port):
        self.host, self.port = host, int(port)
        self.blockSignals(True); self.abort(); self.blockSignals(False)
        self.open(QUrl(f"wss://{host}:{port}/ws"))

    def _ssl(self, errors):
        # Selbstsigniertes Zertifikat: Trust-On-First-Use mit Fingerabdruck-Pinning
        cert = errors[0].certificate() if errors and not errors[0].certificate().isNull() else None
        if cert is None:
            cert = self.sslConfiguration().peerCertificate()
        fp = hashlib.sha256(bytes(cert.toDer())).hexdigest()
        pins = load_json(PINS_FILE, {})
        key = f"{self.host}:{self.port}"
        if pins.get(key) == fp:
            self.ignoreSslErrors(); return
        nice = ":".join(fp[i:i + 2] for i in range(0, 64, 2)).upper()
        if key in pins:
            QMessageBox.critical(self.win, APP, "WARNUNG: Das Server-Zertifikat hat sich geändert!\n\n"
                                 f"Neuer Fingerabdruck:\n{nice}\n\nWenn der Server nicht neu installiert wurde, "
                                 "könnte jemand die Verbindung abhören. Verbindung wird abgebrochen.\n"
                                 "(Zum Zurücksetzen in den Optionen 'Server-Vertrauen zurücksetzen' wählen.)")
            return
        r = QMessageBox.question(self.win, APP, f"Erste Verbindung zu {key}.\n\nZertifikat-Fingerabdruck (SHA-256):\n"
                                 f"{nice}\n\nDiesem Server vertrauen?")
        if r == QMessageBox.Yes:
            pins[key] = fp; save_json(PINS_FILE, pins); self.ignoreSslErrors()

    def _rx(self, txt):
        try:
            self.message.emit(json.loads(txt))
        except Exception:
            pass

    def send(self, obj):
        if self.isValid():
            self.sendTextMessage(json.dumps(obj))
            return True
        return False


# --------------------------------------------------------------------------- Login dialog
class LoginDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.s = win, win.settings
        self.setWindowTitle(f"{APP} - Anmelden"); self.setWindowIcon(app_icon(self.s["accent"]))
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self); lay.setContentsMargins(26, 22, 26, 22); lay.setSpacing(12)
        t = QLabel(APP); t.setObjectName("title"); t.setAlignment(Qt.AlignCenter); lay.addWidget(t)
        sub = QLabel("Sicher chatten - Ende-zu-Ende verschlüsselt"); sub.setObjectName("muted")
        sub.setAlignment(Qt.AlignCenter); lay.addWidget(sub)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        # Login
        w = QWidget(); f = QFormLayout(w)
        self.l_nick = QLineEdit(self.s["last_nick"] if self.s["remember_nick"] else "")
        self.l_pw = QLineEdit(); self.l_pw.setEchoMode(QLineEdit.Password)
        self.l_remember = QCheckBox("Nickname merken"); self.l_remember.setChecked(self.s["remember_nick"])
        f.addRow("Nickname:", self.l_nick); f.addRow("Passwort:", self.l_pw); f.addRow("", self.l_remember)
        self.l_btn = QPushButton("Anmelden"); f.addRow(self.l_btn)
        self.tabs.addTab(w, "Anmelden")
        # Register
        w = QWidget(); f = QFormLayout(w)
        self.r_mail, self.r_nick = QLineEdit(), QLineEdit()
        self.r_mail.setPlaceholderText("für Wartungshinweise"); self.r_nick.setPlaceholderText("3-24 Zeichen")
        self.r_pw, self.r_pw2 = QLineEdit(), QLineEdit()
        for p in (self.r_pw, self.r_pw2): p.setEchoMode(QLineEdit.Password)
        self.r_pw.setPlaceholderText("mindestens 6 Zeichen")
        f.addRow("E-Mail:", self.r_mail); f.addRow("Nickname:", self.r_nick)
        f.addRow("Passwort:", self.r_pw); f.addRow("Wiederholen:", self.r_pw2)
        hint = QLabel("Wichtig: Dein Passwort schützt deinen privaten Schlüssel. Es kann nicht "
                      "wiederhergestellt werden - auch nicht vom Serverbetreiber.")
        hint.setWordWrap(True); hint.setObjectName("muted"); f.addRow(hint)
        self.r_btn = QPushButton("Account erstellen"); f.addRow(self.r_btn)
        self.tabs.addTab(w, "Registrieren")
        # Server
        h = QHBoxLayout()
        self.srv = QLineEdit(self.s["server"]); self.srv.setPlaceholderText("Serveradresse, z. B. chat.example.org"); self.prt = QSpinBox(); self.prt.setRange(1, 65535)
        self.prt.setValue(int(self.s["port"]))
        h.addWidget(QLabel("Server:")); h.addWidget(self.srv, 1); h.addWidget(self.prt); lay.addLayout(h)
        self.status = QLabel(""); self.status.setWordWrap(True); self.status.setObjectName("muted"); lay.addWidget(self.status)
        self.l_btn.clicked.connect(self.do_login); self.r_btn.clicked.connect(self.do_register)
        self.l_pw.returnPressed.connect(self.do_login); self.r_pw2.returnPressed.connect(self.do_register)
        (self.l_pw if self.l_nick.text() else self.l_nick).setFocus()

    def busy(self, on, text=""):
        self.l_btn.setEnabled(not on); self.r_btn.setEnabled(not on); self.status.setText(text)
        QApplication.processEvents()

    def _server(self):
        self.s["server"], self.s["port"] = self.srv.text().strip(), self.prt.value()
        self.win.save_settings()
        return bool(self.s["server"])

    def do_login(self):
        nick, pw = self.l_nick.text().strip(), self.l_pw.text()
        if not nick or not pw:
            return self.status.setText("Bitte Nickname und Passwort eingeben.")
        self.s["remember_nick"] = self.l_remember.isChecked()
        self.s["last_nick"] = nick if self.l_remember.isChecked() else ""
        if not self._server():
            self.srv.setFocus(); return self.status.setText("Bitte zuerst die Adresse deines Herbstchat-Servers eintragen.")
        self.busy(True, "Verbinde ...")
        self.win.start_login(nick, pw, self)

    def do_register(self):
        mail, nick, pw = self.r_mail.text().strip(), self.r_nick.text().strip(), self.r_pw.text()
        if "@" not in mail or "." not in mail.split("@")[-1]:
            return self.status.setText("Bitte eine gültige E-Mail-Adresse angeben.")
        if len(nick) < 3:
            return self.status.setText("Der Nickname muss mindestens 3 Zeichen lang sein.")
        if len(pw) < 6:
            return self.status.setText("Das Passwort muss mindestens 6 Zeichen lang sein.")
        if pw != self.r_pw2.text():
            return self.status.setText("Die Passwörter stimmen nicht überein.")
        if not self._server():
            self.srv.setFocus(); return self.status.setText("Bitte zuerst die Adresse deines Herbstchat-Servers eintragen.")
        self.busy(True, "Erzeuge Schlüssel und registriere ...")
        self.win.start_register(mail, nick, pw, self)

    def fail(self, msg):
        self.busy(False, "<span style='color:#e74c3c'>" + html.escape(msg) + "</span>")

    def registered(self, nick):
        self.tabs.setCurrentIndex(0); self.l_nick.setText(nick); self.l_pw.setText(self.r_pw.text())
        self.busy(False, "<span style='color:#3bb54a'>Account erstellt - du wirst angemeldet ...</span>")
        self.do_login()


# --------------------------------------------------------------------------- Options
class OptionsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, s = win, dict(win.settings)
        self.setWindowTitle(f"{APP} - Optionen"); self.setMinimumWidth(680)
        lay = QVBoxLayout(self); tabs = QTabWidget(); lay.addWidget(tabs)
        self.w = {}

        def cb(key, text):
            c = QCheckBox(text); c.setChecked(bool(s[key])); self.w[key] = c; return c

        # Darstellung
        p = QWidget(); f = QFormLayout(p)
        ff = QFontComboBox(); ff.setCurrentFont(QFont(s["font_family"] or QApplication.font().family())); self.w["font_family"] = ff
        fs = QSpinBox(); fs.setRange(8, 24); fs.setValue(s["font_size"]); fs.setSuffix(" pt"); self.w["font_size"] = fs
        th = QComboBox(); th.addItems(["hell", "dunkel"]); th.setCurrentText(s["theme"]); self.w["theme"] = th
        ac = QComboBox()
        self.accents = dict(ACCENTS)
        ac.addItems(list(self.accents)); self.w["accent"] = ac
        for k, v in self.accents.items():
            if v == s["accent"]: ac.setCurrentText(k)
        f.addRow("Schriftart:", ff); f.addRow("Schriftgröße:", fs); f.addRow("Farbschema:", th); f.addRow("Akzentfarbe:", ac)
        f.addRow(cb("show_time", "Uhrzeit bei Nachrichten anzeigen"))
        f.addRow(cb("compact", "Kompakte Nachrichtenansicht"))
        f.addRow(cb("show_offline", "Offline-Kontakte in der Liste anzeigen"))
        tabs.addTab(p, "Darstellung")
        # Töne
        p = QWidget(); f = QFormLayout(p)
        f.addRow(cb("sound_on", "Töne aktivieren"))
        f.addRow(cb("sound_msg", "Ton bei eingehender Nachricht (\"Uh-oh\")"))
        f.addRow(cb("sound_sent", "Ton beim Senden"))
        f.addRow(cb("sound_online", "Ton wenn ein Kontakt online kommt"))
        f.addRow(cb("sound_dnd_busy", "Keine Töne im Status \"Beschäftigt\""))
        vol = QSlider(Qt.Horizontal); vol.setRange(0, 100); vol.setValue(s["volume"]); self.w["volume"] = vol
        f.addRow("Lautstärke:", vol)
        t = QPushButton("Ton testen"); t.clicked.connect(lambda: win.play("msg", force=True, vol=vol.value())); f.addRow(t)
        tabs.addTab(p, "Töne")
        # Benachrichtigungen
        p = QWidget(); f = QFormLayout(p)
        f.addRow(cb("notify", "Desktop-Benachrichtigung bei neuer Nachricht"))
        f.addRow(cb("notify_preview", "Nachrichtenvorschau in Benachrichtigung zeigen"))
        f.addRow(cb("flash_taskbar", "Taskleiste/Dock aufblinken lassen"))
        tabs.addTab(p, "Benachrichtigungen")
        # Chat & Privatsphäre
        p = QWidget(); f = QFormLayout(p)
        f.addRow(cb("enter_sends", "Enter sendet (Umschalt+Enter = neue Zeile)"))
        f.addRow(cb("send_typing", "Anderen anzeigen, dass ich tippe"))
        f.addRow(cb("save_history", "Chatverlauf lokal (verschlüsselt) speichern"))
        clr = QPushButton("Gesamten lokalen Chatverlauf löschen"); clr.setProperty("flat", True)
        clr.clicked.connect(win.clear_history); f.addRow(clr)
        tabs.addTab(p, "Chat && Privatsphäre")
        # System
        p = QWidget(); f = QFormLayout(p)
        f.addRow(cb("tray", "Beim Schließen in den Infobereich (Tray) minimieren"))
        f.addRow(cb("start_minimized", "Minimiert starten"))
        ss = QComboBox(); [ss.addItem(STATUS[k][0], k) for k in ("online", "away", "busy", "invisible")]
        ss.setCurrentIndex(["online", "away", "busy", "invisible"].index(s["start_status"])); self.w["start_status"] = ss
        f.addRow("Status beim Anmelden:", ss)
        srv = QLineEdit(s["server"]); srv.setPlaceholderText("z. B. chat.example.org"); self.w["server"] = srv
        prt = QSpinBox(); prt.setRange(1, 65535); prt.setValue(int(s["port"])); self.w["port"] = prt
        f.addRow("Server:", srv); f.addRow("Port:", prt)
        rp = QPushButton("Server-Vertrauen zurücksetzen"); rp.setProperty("flat", True)
        rp.clicked.connect(lambda: (save_json(PINS_FILE, {}), QMessageBox.information(self, APP, "Zertifikats-Pins gelöscht.")))
        f.addRow(rp)
        tabs.addTab(p, "System")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.button(QDialogButtonBox.RestoreDefaults).setText("Standard")
        bb.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        bb.accepted.connect(self.ok); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.defaults)
        lay.addWidget(bb)

    def defaults(self):
        keep = {k: self.win.settings[k] for k in ("server", "port", "last_nick")}
        self.win.settings.update(DEFAULTS); self.win.settings.update(keep)
        self.win.apply_settings(); self.accept()

    def ok(self):
        s = self.win.settings
        for k, w in self.w.items():
            if isinstance(w, QCheckBox): s[k] = w.isChecked()
            elif k == "font_family": s[k] = w.currentFont().family()
            elif k == "accent": s[k] = self.accents[w.currentText()]
            elif k == "start_status": s[k] = w.currentData()
            elif isinstance(w, (QSpinBox, QSlider)): s[k] = w.value()
            elif isinstance(w, QComboBox): s[k] = w.currentText()
            elif isinstance(w, QLineEdit): s[k] = w.text().strip()
        self.win.apply_settings(); self.accept()


# --------------------------------------------------------------------------- Input box
class InputBox(QPlainTextEdit):
    send = Signal()
    typing = Signal()

    def __init__(self, win):
        super().__init__(); self.win = win
        self.setPlaceholderText("Nachricht schreiben ..."); self.setFixedHeight(80)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            shift = bool(e.modifiers() & Qt.ShiftModifier)
            ctrl = bool(e.modifiers() & Qt.ControlModifier)
            if (self.win.settings["enter_sends"] and not shift) or ctrl:
                self.send.emit(); return
        super().keyPressEvent(e)
        if e.text():
            self.typing.emit()


# --------------------------------------------------------------------------- Main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = dict(DEFAULTS); self.settings.update(load_json(SETTINGS_FILE, {}))
        if self.settings.get("accent") not in ACCENTS.values():   # z. B. altes Herbst-Orange
            self.settings["accent"] = ACCENT_DEFAULT
        self.sounds = make_sounds(); self.effects = {}
        self.conn = Connection(self)
        self.conn.message.connect(self.on_msg); self.conn.state.connect(self.on_state)
        self.me = None; self.auth = self.vault = self.priv = None
        self.contacts = {}       # id -> {nick, pubkey, status}
        self.profile = {"history": {}, "keys": {}, "unread": {}, "names": {}}
        self.current = None; self.pending = {}; self.pending_action = None
        self.manual_logout = False; self.typing_sent = 0; self.typing_from = {}
        self.upload_queue = []          # Chunks für den einmaligen Import des alten Verlaufs
        self.setWindowTitle(APP); self.setWindowIcon(app_icon(self.settings["accent"])); self.resize(980, 660)
        self.build_ui(); self.build_tray(); self.apply_settings(save=False)
        self.reconnect_timer = QTimer(self, interval=5000, timeout=self.reconnect)
        self.ping_timer = QTimer(self, interval=25000, timeout=lambda: self.conn.send({"t": "ping"}))
        self.typing_timer = QTimer(self, interval=1500, timeout=self.update_typing); self.typing_timer.start()

    # ---- UI
    def build_ui(self):
        mb = self.menuBar()
        m = mb.addMenu("&Herbstchat")
        self.act(m, "Optionen ...", self.options, "Ctrl+,")
        self.act(m, "Passwort ändern ...", self.change_password)
        self.act(m, "E-Mail-Adresse ändern ...", self.change_email)
        self.act(m, "Mein Schlüssel-Fingerabdruck", self.my_fingerprint)
        m.addSeparator(); self.act(m, "Abmelden", self.logout); self.act(m, "Beenden", self.quit, "Ctrl+Q")
        m = mb.addMenu("&Kontakte")
        self.act(m, "Kontakt hinzufügen ...", self.add_contact, "Ctrl+N")
        self.act(m, "Kontakt entfernen", self.remove_contact)
        self.act(m, "Sicherheitsnummer prüfen", self.verify_contact)
        self.act(m, "Verlauf mit Kontakt löschen", self.clear_chat)
        m = mb.addMenu("&Status")
        for k in ("online", "away", "busy", "invisible"):
            self.act(m, STATUS[k][0], lambda k=k: self.set_status(k))
        m = mb.addMenu("&Info")
        self.act(m, "Info über Herbstchat ...", self.info, "F1")
        self.act(m, "Webseite herbstleyd.org", lambda: QDesktopServices.openUrl(QUrl(WEBSITE)))

        central = QWidget(); root = QHBoxLayout(central); root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(); root.addWidget(split); self.setCentralWidget(central)
        # left
        left = QWidget(objectName="panel"); ll = QVBoxLayout(left); ll.setContentsMargins(10, 10, 10, 10)
        self.me_label = QLabel(APP); self.me_label.setObjectName("chathead"); ll.addWidget(self.me_label)
        self.filter = QLineEdit(placeholderText="Kontakte durchsuchen ..."); self.filter.textChanged.connect(self.refresh_contacts)
        ll.addWidget(self.filter)
        self.list = QListWidget(); self.list.setIconSize(QSize(22, 22)); self.list.currentItemChanged.connect(self.select_contact)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu); self.list.customContextMenuRequested.connect(self.contact_menu)
        ll.addWidget(self.list, 1)
        add = QPushButton("+ Kontakt hinzufügen"); add.clicked.connect(self.add_contact); ll.addWidget(add)
        self.status_box = QComboBox()
        for k in ("online", "away", "busy", "invisible"):
            self.status_box.addItem(dot_icon(STATUS[k][1]), STATUS[k][0], k)
        self.status_box.activated.connect(lambda i: self.set_status(self.status_box.itemData(i)))
        ll.addWidget(self.status_box)
        self.conn_label = QLabel("Nicht verbunden"); self.conn_label.setObjectName("muted"); ll.addWidget(self.conn_label)
        split.addWidget(left)
        # right
        right = QWidget(objectName="panel"); rl = QVBoxLayout(right); rl.setContentsMargins(12, 10, 12, 10)
        hh = QHBoxLayout(); self.chat_head = QLabel("Wähle links einen Kontakt"); self.chat_head.setObjectName("chathead")
        hh.addWidget(self.chat_head, 1)
        self.lock_label = QLabel("🔒 Ende-zu-Ende verschlüsselt"); self.lock_label.setObjectName("muted"); hh.addWidget(self.lock_label)
        rl.addLayout(hh)
        self.view = QTextBrowser(); self.view.setOpenExternalLinks(True); rl.addWidget(self.view, 1)
        self.typing_label = QLabel(""); self.typing_label.setObjectName("muted"); rl.addWidget(self.typing_label)
        ih = QHBoxLayout()
        self.emoji_btn = QToolButton(); self.emoji_btn.setText("😀"); self.emoji_btn.setPopupMode(QToolButton.InstantPopup)
        em = QMenu(self); grid = QWidget(); g = QGridLayout(grid); g.setSpacing(2)
        for i, e in enumerate(EMOJIS):
            b = QToolButton(); b.setText(e); b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, e=e: (self.input.insertPlainText(e), em.close(), self.input.setFocus()))
            g.addWidget(b, i // 8, i % 8)
        from PySide6.QtWidgets import QWidgetAction
        wa = QWidgetAction(em); wa.setDefaultWidget(grid); em.addAction(wa); self.emoji_btn.setMenu(em)
        self.input = InputBox(self); self.input.send.connect(self.send_message); self.input.typing.connect(self.on_typing)
        self.send_btn = QPushButton("Senden"); self.send_btn.clicked.connect(self.send_message)
        ih.addWidget(self.emoji_btn, 0, Qt.AlignBottom); ih.addWidget(self.input, 1); ih.addWidget(self.send_btn, 0, Qt.AlignBottom)
        rl.addLayout(ih)
        split.addWidget(right); split.setSizes([280, 700])
        self.set_chat_enabled(False)

    def act(self, menu, text, fn, sc=None):
        a = QAction(text, self); a.triggered.connect(fn)
        if sc: a.setShortcut(QKeySequence(sc))
        menu.addAction(a); return a

    def build_tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(app_icon(self.settings["accent"]), self)
            m = QMenu(); m.addAction("Öffnen", self.show_normal)
            for k in ("online", "away", "busy", "invisible"):
                m.addAction(STATUS[k][0], lambda k=k: self.set_status(k))
            m.addSeparator(); m.addAction("Beenden", self.quit)
            self.tray.setContextMenu(m); self.tray.setToolTip(APP)
            self.tray.activated.connect(lambda r: self.show_normal() if r == QSystemTrayIcon.Trigger else None)
            self.tray.messageClicked.connect(self.show_normal)
            self.tray.show()

    def show_normal(self):
        self.show(); self.setWindowState(self.windowState() & ~Qt.WindowMinimized); self.raise_(); self.activateWindow()

    def apply_settings(self, save=True):
        QApplication.instance().setStyleSheet(stylesheet(self.settings))
        self.setWindowIcon(app_icon(self.settings["accent"]))
        if self.tray: self.tray.setIcon(app_icon(self.settings["accent"]))
        if save: self.save_settings()
        self.refresh_contacts(); self.render_chat()

    def save_settings(self):
        save_json(SETTINGS_FILE, self.settings)

    def set_chat_enabled(self, on):
        for w in (self.input, self.send_btn, self.emoji_btn): w.setEnabled(on)

    # ---- sound / notify
    def play(self, kind, force=False, vol=None):
        s = self.settings
        if not force:
            if not s["sound_on"] or not s.get("sound_" + kind, True): return
            if s["sound_dnd_busy"] and self.status_box.currentData() == "busy": return
        if QSoundEffect is None:
            QApplication.beep(); return
        eff = self.effects.get(kind)
        if eff is None:
            eff = QSoundEffect(self); eff.setSource(QUrl.fromLocalFile(self.sounds[kind])); self.effects[kind] = eff
        eff.setVolume((vol if vol is not None else s["volume"]) / 100.0); eff.play()

    def notify(self, title, text):
        if self.settings["flash_taskbar"]:
            QApplication.alert(self, 0)
        if self.settings["notify"] and self.tray and (not self.isActiveWindow() or self.isMinimized()):
            self.tray.showMessage(title, text if self.settings["notify_preview"] else "Neue Nachricht",
                                  app_icon(self.settings["accent"]), 5000)

    # ---- login / register
    def start_login(self, nick, pw, dlg):
        self.login_dlg = dlg
        self.pending_action = ("login", nick, pw)
        self.manual_logout = False
        self.conn.open_to(self.settings["server"], self.settings["port"])

    def start_register(self, mail, nick, pw, dlg):
        self.login_dlg = dlg
        self.pending_action = ("register", mail, nick, pw)
        self.conn.open_to(self.settings["server"], self.settings["port"])

    def on_state(self, st):
        if st == "connected":
            self.conn_label.setText("Verbunden mit " + self.settings["server"])
            self.reconnect_timer.stop(); self.ping_timer.start()
            pa = self.pending_action
            if pa and pa[0] == "register":
                _, mail, nick, pw = pa
                salt = nacl.utils.random(argon2id.SALTBYTES)
                auth, vault = derive(pw, salt)
                priv = nacl.public.PrivateKey.generate()
                enc = nacl.secret.SecretBox(vault).encrypt(bytes(priv))
                self.conn.send({"t": "register", "email": mail, "nick": nick, "salt": b64e(salt), "auth": b64e(auth),
                                "pubkey": b64e(bytes(priv.public_key)), "enc_priv": b64e(enc)})
            elif pa and pa[0] == "login":
                self.conn.send({"t": "prelogin", "nick": pa[1]})
            elif self.me and self.auth:      # automatischer Reconnect
                self.conn.send({"t": "login", "nick": self.me["nick"], "auth": b64e(self.auth),
                                "status": self.status_box.currentData()})
        else:
            self.ping_timer.stop()
            self.conn_label.setText("Verbindung getrennt - neuer Versuch ...")
            for c in self.contacts.values(): c["status"] = "offline"
            self.refresh_contacts()
            if self.pending_action and getattr(self, "login_dlg", None) and self.login_dlg.isVisible():
                err = self.conn.errorString() or "Server nicht erreichbar."
                self.login_dlg.fail("Verbindung fehlgeschlagen: " + err); self.pending_action = None
            elif self.me and not self.manual_logout:
                self.reconnect_timer.start()

    def reconnect(self):
        if self.me and not self.manual_logout:
            self.conn.open_to(self.settings["server"], self.settings["port"])

    def on_msg(self, d):
        t = d.get("t")
        if t == "salt" and self.pending_action and self.pending_action[0] == "login":
            _, nick, pw = self.pending_action
            self.login_dlg.status.setText("Prüfe Passwort ...") ; QApplication.processEvents()
            self.kdf_salt = b64d(d["salt"])
            self.auth, self.vault = derive(pw, self.kdf_salt)
            self.conn.send({"t": "login", "nick": nick, "auth": b64e(self.auth), "status": self.settings["start_status"]})
        elif t == "register_ok":
            nick = self.pending_action[2]; self.pending_action = None
            self.login_dlg.registered(nick)
        elif t == "login_ok":
            self.login_ok(d)
        elif t == "error":
            ctx = d.get("ctx")
            if ctx in ("login", "register") and self.pending_action:
                self.pending_action = None; self.login_dlg.fail(d.get("msg", "Fehler"))
                self.conn.close()
            elif ctx == "login":
                self.manual_logout = True; self.reconnect_timer.stop()
                QMessageBox.warning(self, APP, d.get("msg")); self.logout()
            elif ctx == "msg":
                self.mark_failed(d.get("cid"), d.get("msg"))
            else:
                QMessageBox.warning(self, APP, d.get("msg", "Fehler"))
        elif t == "msg":
            self.incoming(d)
        elif t == "sent":
            self.mark_sent(d)
        elif t == "presence":
            c = self.contacts.get(d["id"])
            if c:
                was = c["status"]; c["status"] = d["status"]
                if was == "offline" and d["status"] != "offline":
                    self.play("online")
                self.refresh_contacts()
                if self.current == d["id"]: self.update_head()
        elif t == "contact":
            self.add_known(d["contact"]); self.refresh_contacts(select=d["contact"]["id"])
        elif t == "contact_removed":
            self.contacts.pop(d["id"], None); self.refresh_contacts()
        elif t == "search":
            self.search_results(d["results"])
        elif t == "typing":
            self.typing_from[d["from"]] = time.time(); self.update_typing()
        elif t == "renamed":
            if d.get("self") and self.me:
                self.me["nick"] = d["nick"]; self.update_me()
                QMessageBox.information(self, APP, f"Dein Nickname wurde vom Administrator in \"{d['nick']}\" geändert.")
            elif d["id"] in self.contacts:
                self.contacts[d["id"]]["nick"] = d["nick"]; self.profile["names"][str(d["id"])] = d["nick"]
                self.refresh_contacts(); self.update_head()
        elif t == "notice":
            self.play("notice", force=self.settings["sound_on"])
            self.notify("Herbstchat - Systemnachricht", d.get("text", ""))
            QMessageBox.information(self, "Systemnachricht vom Administrator", d.get("text", ""))
        elif t == "kicked":
            self.manual_logout = True; self.reconnect_timer.stop()
            QMessageBox.warning(self, APP, d.get("reason", "Verbindung getrennt.")); self.logout()
        elif t == "password_ok":
            old_path = self.profile_path()
            self.kdf_salt, self.auth, self.vault = self.pw_pending
            self.save_profile()
            QMessageBox.information(self, APP, "Passwort erfolgreich geändert.")
        elif t == "email_ok":
            self.me["email"] = d["email"]; QMessageBox.information(self, APP, "E-Mail-Adresse geändert.")
        elif t == "history_delta":
            self.history_merge(d)
        elif t == "history_uploaded":
            self.history_upload_next()
        elif t == "msg_copy":
            self.msg_copy(d)
        elif t == "user":
            self.add_known(d["user"], persist_contact=False)

    def login_ok(self, d):
        first = self.me is None
        if first:
            try:
                self.priv = nacl.public.PrivateKey(nacl.secret.SecretBox(self.vault).decrypt(b64d(d["enc_priv"])))
            except Exception:
                self.login_dlg.fail("Privater Schlüssel konnte nicht entschlüsselt werden."); return
            self.me = {"id": d["id"], "nick": d["nick"], "email": d["email"], "pubkey": d["pubkey"]}
            self.load_profile()
            st = self.settings["start_status"]
            self.status_box.setCurrentIndex(["online", "away", "busy", "invisible"].index(st))
            self.pending_action = None
            if getattr(self, "login_dlg", None): self.login_dlg.accept()
            self.save_settings()
        self.contacts = {}
        for c in d["contacts"]:
            self.add_known(c)
        self.update_me(); self.refresh_contacts(); self.set_chat_enabled(self.current is not None)
        self.upload_queue = []
        if "history_counter" in d:          # Server >= 1.1 kann Verlauf synchronisieren
            self.conn.send({"t": "history_delta", "since": int(self.profile.get("history_last", 0))})
        if first and not self.settings["start_minimized"]:
            self.show_normal()
        elif first and self.tray:
            self.hide()
        if first and d.get("motd"):
            QMessageBox.information(self, "Nachricht des Tages", d["motd"])
        for cid, item in list(self.pending.items()):     # nach Reconnect erneut senden
            self.conn.send(item)

    def update_me(self):
        self.me_label.setText(f"👤 {self.me['nick']}" if self.me else APP)
        self.setWindowTitle(f"{APP} - {self.me['nick']}" if self.me else APP)

    # ---- profile (lokal, verschlüsselt)
    # ---- Verlauf über Geräte synchronisieren (Server speichert nur Chiffretext)
    @staticmethod
    def _hkey(me, ts, text):
        return (bool(me), round(float(ts), 3), text)

    def history_merge(self, d):
        for k, u in (d.get("users") or {}).items():
            if u and u.get("pubkey") and k not in self.profile["keys"]:
                self.profile["keys"][k] = u["pubkey"]
            if u and u.get("nick"):
                self.profile["names"].setdefault(k, u["nick"])
        touched, index = set(), {}
        for e in d.get("delta", []):
            key = str(e["contact_id"]); box = self.box(e["contact_id"])
            if not box:
                continue
            try:
                text = str(json.loads(box.decrypt(b64d(e["blob"]))).get("text", ""))
            except Exception:
                continue
            hist = self.history(key)
            if key not in index:
                index[key] = ({m.get("cid"): m for m in hist if m.get("cid")},
                              {self._hkey(m.get("me"), m.get("ts", 0), m.get("text")) for m in hist if not m.get("sys")})
            by_cid, seen = index[key]
            me = bool(e.get("out"))
            if me and e.get("cid") and e["cid"] in by_cid:
                m = by_cid[e["cid"]]
                if m.get("state") in ("sending", None): m["state"] = "sent"
                m.setdefault("h", e["id"]); continue
            hk = self._hkey(me, e["ts"], text)
            if hk in seen:
                continue
            m = {"me": me, "text": text, "ts": e["ts"], "h": e["id"]}
            if me:
                m["state"] = "sent"
                if e.get("cid"): m["cid"] = e["cid"]; by_cid[e["cid"]] = m
            hist.append(m); seen.add(hk); touched.add(key)
        for key in touched:
            self.history(key).sort(key=lambda m: m.get("ts", 0))
        self.profile["history_last"] = max(int(self.profile.get("history_last", 0)), int(d.get("last", 0)))
        self.save_profile()
        if touched:
            self.refresh_contacts()
            if str(self.current) in touched: self.render_chat()
        if d.get("more"):
            self.conn.send({"t": "history_delta", "since": self.profile["history_last"]})
        elif not self.profile.get("legacy_uploaded"):
            self.history_upload_start()

    def history_upload_start(self):
        """Einmalig: lokalen Verlauf von vor 1.1.2 hochladen, damit andere Geräte ihn sehen."""
        cutoff = self.profile.setdefault("sync_start", time.time())
        chunk, size = [], 0
        for key, msgs in self.profile["history"].items():
            box = self.box(key)
            if not box: continue
            for m in msgs:
                if m.get("sys") or "h" in m or m.get("ts", 0) >= cutoff or m.get("state") in ("sending", "failed"):
                    continue
                blob = b64e(box.encrypt(json.dumps({"text": m.get("text", ""), "ts": m["ts"]}).encode()))
                if chunk and (len(chunk) >= 150 or size + len(blob) > 90000):
                    self.upload_queue.append(chunk); chunk, size = [], 0
                chunk.append(({"contact_id": int(key), "out": bool(m.get("me")), "blob": blob, "ts": m["ts"]}, m))
                size += len(blob) + 80
        if chunk: self.upload_queue.append(chunk)
        self.history_upload_next(first=True)

    def history_upload_next(self, first=False):
        if not first and self.upload_queue:
            for _, m in self.upload_queue.pop(0):
                m["h"] = 0          # hochgeladen
        if self.upload_queue:
            self.conn.send({"t": "history_upload", "hv": 2, "entries": [e for e, _ in self.upload_queue[0]]})
        else:
            if not self.profile.get("legacy_uploaded"):
                self.profile["legacy_uploaded"] = True; self.save_profile()

    def msg_copy(self, d):
        """Nachricht, die ich auf einem anderen Gerät gesendet habe."""
        to = d["to"]; key = str(to)
        if d.get("to_pubkey") and key not in self.profile["keys"]: self.profile["keys"][key] = d["to_pubkey"]
        if d.get("to_nick"): self.profile["names"][key] = d["to_nick"]
        box = self.box(to)
        try:
            text = str(json.loads(box.decrypt(b64d(d["payload"]))).get("text", ""))
        except Exception:
            return
        if d.get("cid") and self.find_cid(d["cid"]): return
        self.history(to).append({"me": True, "text": text, "ts": d.get("ts", time.time()), "cid": d.get("cid"),
                                 "state": "sent", "h": d.get("hid", 0)})
        self.save_profile(); self.refresh_contacts()
        if self.current == to: self.render_chat()

    def profile_path(self):
        return os.path.join(DATA_DIR, f"profile_{self.me['id']}_{self.settings['server']}.dat")

    def load_profile(self):
        try:
            raw = open(self.profile_path(), "rb").read()
            self.profile = json.loads(nacl.secret.SecretBox(self.vault).decrypt(raw))
        except Exception:
            self.profile = {"history": {}, "keys": {}, "unread": {}, "names": {}}
        for k in ("history", "keys", "unread", "names"):
            self.profile.setdefault(k, {})
        self.profile.setdefault("history_last", 0)
        if not self.profile["history"]:      # nichts Altes zum Hochladen
            self.profile.setdefault("legacy_uploaded", True)
        self.profile.setdefault("sync_start", time.time())

    def save_profile(self):
        if not self.me: return
        p = dict(self.profile)
        if not self.settings["save_history"]:
            p = dict(p, history={})
        data = nacl.secret.SecretBox(self.vault).encrypt(json.dumps(p).encode())
        with open(self.profile_path() + ".tmp", "wb") as f: f.write(data)
        os.replace(self.profile_path() + ".tmp", self.profile_path())

    def clear_history(self):
        if QMessageBox.question(self, APP, "Gesamten Chatverlauf löschen?\n\nDer Verlauf wird auf diesem Gerät und auf dem "
                                "Server gelöscht und ist danach auch auf deinen anderen Geräten nicht mehr abrufbar.") == QMessageBox.Yes:
            self.profile["history"] = {}; self.profile["unread"] = {}; self.save_profile(); self.render_chat(); self.refresh_contacts()
            if self.me: self.conn.send({"t": "history_clear"})

    def clear_chat(self):
        if self.current and QMessageBox.question(self, APP, "Verlauf mit diesem Kontakt löschen?\n\n"
                                                 "(auch auf dem Server und damit auf allen deinen Geräten)") == QMessageBox.Yes:
            self.profile["history"].pop(str(self.current), None); self.save_profile(); self.render_chat()
            self.conn.send({"t": "history_clear", "contact_id": self.current})

    # ---- contacts
    def add_known(self, c, persist_contact=True):
        key = str(c["id"]); known = self.profile["keys"].get(key)
        if known and known != c["pubkey"]:
            self.history(c["id"]).append({"sys": True, "text": "⚠ Der Schlüssel dieses Kontakts hat sich geändert. "
                                          "Bitte Sicherheitsnummer prüfen!", "ts": time.time()})
        self.profile["keys"][key] = c["pubkey"]; self.profile["names"][key] = c["nick"]
        if persist_contact:
            self.contacts[c["id"]] = {"nick": c["nick"], "pubkey": c["pubkey"], "status": c.get("status", "offline")}

    def refresh_contacts(self, select=None):
        if not hasattr(self, "list"): return
        cur = select if select is not None else self.current
        self.list.blockSignals(True); self.list.clear()
        flt = self.filter.text().lower()
        order = {"online": 0, "away": 1, "busy": 2, "offline": 3}
        ids = set(self.contacts) | {int(k) for k, v in self.profile.get("unread", {}).items() if v}
        rows = []
        for cid in ids:
            c = self.contacts.get(cid) or {"nick": self.profile["names"].get(str(cid), f"#{cid}"), "status": "offline"}
            if flt and flt not in c["nick"].lower(): continue
            if not self.settings["show_offline"] and c["status"] == "offline" and cid != cur and not self.profile["unread"].get(str(cid)):
                continue
            rows.append((order.get(c["status"], 3), c["nick"].lower(), cid, c))
        for _, _, cid, c in sorted(rows):
            un = self.profile["unread"].get(str(cid), 0)
            label = c["nick"] + ("" if cid in self.contacts else "  (nicht in Kontakten)")
            it = QListWidgetItem(dot_icon(STATUS[c["status"]][1], un), label)
            it.setData(Qt.UserRole, cid); it.setToolTip(STATUS[c["status"]][0])
            if un: f = it.font(); f.setBold(True); it.setFont(f)
            self.list.addItem(it)
            if cid == cur: self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if select is not None: self.select_contact(self.list.currentItem())

    def select_contact(self, item, _prev=None):
        if not item: return
        self.current = item.data(Qt.UserRole)
        if self.profile["unread"].pop(str(self.current), None):
            self.save_profile(); QTimer.singleShot(0, self.refresh_contacts)
        self.set_chat_enabled(True); self.update_head(); self.render_chat(); self.input.setFocus()

    def update_head(self):
        if self.current is None: return
        c = self.contacts.get(self.current)
        nick = c["nick"] if c else self.profile["names"].get(str(self.current), "?")
        st = STATUS[c["status"] if c else "offline"]
        self.chat_head.setText(f"{html.escape(nick)}  <span style='color:{st[1]};font-size:small'>● {st[0]}</span>")

    def contact_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it: return
        cid = it.data(Qt.UserRole); m = QMenu(self)
        if cid not in self.contacts:
            m.addAction("Zu Kontakten hinzufügen", lambda: self.conn.send({"t": "add_contact", "id": cid}))
        m.addAction("Sicherheitsnummer prüfen", self.verify_contact)
        m.addAction("Verlauf löschen", self.clear_chat)
        m.addAction("Kontakt entfernen", self.remove_contact)
        m.exec(self.list.mapToGlobal(pos))

    def add_contact(self):
        if not self.me: return
        nick, ok = QInputDialog.getText(self, "Kontakt hinzufügen", "Nickname suchen (Anfang genügt):")
        if ok and nick.strip():
            self.conn.send({"t": "search", "q": nick.strip()})

    def search_results(self, res):
        if not res:
            return QMessageBox.information(self, APP, "Kein Benutzer gefunden.")
        names = [r["nick"] for r in res]
        nick, ok = QInputDialog.getItem(self, "Kontakt hinzufügen", "Gefundene Benutzer:", names, 0, False)
        if ok:
            self.conn.send({"t": "add_contact", "id": res[names.index(nick)]["id"]})

    def remove_contact(self):
        if self.current in self.contacts and QMessageBox.question(
                self, APP, f"{self.contacts[self.current]['nick']} aus der Kontaktliste entfernen?") == QMessageBox.Yes:
            self.conn.send({"t": "remove_contact", "id": self.current})

    def verify_contact(self):
        if self.current is None: return
        pk = self.profile["keys"].get(str(self.current))
        if not pk: return
        QMessageBox.information(self, "Sicherheitsnummer",
            f"Sicherheitsnummer mit {self.profile['names'].get(str(self.current))}:\n\n{safety_number(self.me['pubkey'], pk)}\n\n"
            "Vergleicht diese Nummer z.B. persönlich oder telefonisch. Stimmt sie bei beiden überein, "
            "kann niemand - auch nicht der Server - eure Nachrichten mitlesen.")

    def my_fingerprint(self):
        if not self.me: return
        fp = hashlib.sha256(b64d(self.me["pubkey"])).hexdigest()[:32]
        QMessageBox.information(self, APP, "Dein Schlüssel-Fingerabdruck:\n\n" + " ".join(fp[i:i+4] for i in range(0, 32, 4)))

    # ---- messages
    def history(self, cid):
        return self.profile["history"].setdefault(str(cid), [])

    def box(self, cid):
        pk = self.profile["keys"].get(str(cid))
        return nacl.public.Box(self.priv, nacl.public.PublicKey(b64d(pk))) if pk else None

    def send_message(self):
        text = self.input.toPlainText().strip()
        if not text or self.current is None or not self.me: return
        box = self.box(self.current)
        if not box: return
        cid = uuid.uuid4().hex
        payload = b64e(box.encrypt(json.dumps({"text": text, "ts": time.time()}).encode()))
        item = {"t": "msg", "to": self.current, "payload": payload, "cid": cid}
        self.pending[cid] = item
        self.history(self.current).append({"me": True, "text": text, "ts": time.time(), "cid": cid, "state": "sending"})
        self.input.clear(); self.conn.send(item); self.play("sent")
        self.save_profile(); self.render_chat()

    def find_cid(self, cid):
        for cid_, h in self.profile["history"].items():
            for m in reversed(h[-200:]):
                if m.get("cid") == cid: return m
        return None

    def mark_sent(self, d):
        self.pending.pop(d.get("cid"), None)
        m = self.find_cid(d.get("cid"))
        if m:
            m["state"] = "queued" if d.get("queued") else "sent"; self.save_profile(); self.render_chat()

    def mark_failed(self, cid, msg):
        self.pending.pop(cid, None)
        m = self.find_cid(cid)
        if m: m["state"] = "failed"; m["err"] = msg; self.save_profile(); self.render_chat()
        QMessageBox.warning(self, APP, msg or "Senden fehlgeschlagen.")

    def incoming(self, d):
        sender = d["from"]
        if d.get("from_pubkey") and str(sender) not in self.profile["keys"]:
            self.profile["keys"][str(sender)] = d["from_pubkey"]
        if d.get("from_nick"): self.profile["names"][str(sender)] = d["from_nick"]
        box = self.box(sender)
        try:
            obj = json.loads(box.decrypt(b64d(d["payload"])))
            text = str(obj.get("text", ""))
        except Exception:
            text = "[Nachricht konnte nicht entschlüsselt werden]"
        m = {"me": False, "text": text, "ts": d.get("ts", time.time())}
        if d.get("hid"): m["h"] = d["hid"]
        self.history(sender).append(m)
        self.conn.send({"t": "ack", "ids": [d["id"]]})
        self.typing_from.pop(sender, None)
        visible = self.current == sender and self.isActiveWindow() and not self.isMinimized()
        if self.current != sender:
            self.profile["unread"][str(sender)] = self.profile["unread"].get(str(sender), 0) + 1
        self.save_profile(); self.refresh_contacts()
        if self.current == sender: self.render_chat()
        if not visible:
            self.play("msg"); self.notify(f"Nachricht von {self.profile['names'].get(str(sender), '?')}", text[:120])

    def on_typing(self):
        if self.settings["send_typing"] and self.current and time.time() - self.typing_sent > 3:
            self.typing_sent = time.time(); self.conn.send({"t": "typing", "to": self.current})

    def update_typing(self):
        t = self.typing_from.get(self.current)
        if t and time.time() - t < 5:
            self.typing_label.setText(f"{self.profile['names'].get(str(self.current), '')} schreibt ...")
        else:
            self.typing_label.setText("")

    def render_chat(self):
        if not hasattr(self, "view"): return
        if self.current is None:
            self.view.setHtml("<div style='color:#888;text-align:center;margin-top:80px'>"
                              "<h2>Willkommen bei Herbstchat</h2><p>Wähle links einen Kontakt oder füge einen neuen hinzu.</p></div>")
            return
        dark = self.settings["theme"] == "dunkel"; a = self.settings["accent"]
        other_bg = "#2c333d" if dark else "#e3eaf3"; txt = "#e6e9ee" if dark else "#1c2430"
        pad = 4 if self.settings["compact"] else 8
        out, last_day = [], None
        nick = self.profile["names"].get(str(self.current), "")
        for m in self.history(self.current)[-500:]:
            dt = datetime.datetime.fromtimestamp(m["ts"])
            day = dt.strftime("%d.%m.%Y")
            if day != last_day:
                out.append(f"<p align=center style='color:#999;font-size:small'>— {day} —</p>"); last_day = day
            if m.get("sys"):
                out.append(f"<p align=center style='color:#4da3ff'>{html.escape(m['text'])}</p>"); continue
            body = html.escape(m["text"]).replace("\n", "<br>")
            import re
            body = re.sub(r"(https?://[^\s<]+)", r"<a href='\1' style='color:inherit'>\1</a>", body)
            tm = dt.strftime("%H:%M") if self.settings["show_time"] else ""
            if m.get("me"):
                tick = {"sending": "⏳", "sent": "✓", "queued": "✉ (zugestellt sobald online)", "failed": "⚠"}.get(m.get("state"), "✓")
                out.append(f"""<table width=100% cellspacing=0 cellpadding=0 style='margin:2px 0'><tr><td width=25%></td>
<td align=right><table cellpadding={pad} style='background:{a};border-radius:10px'><tr><td style='color:white'>{body}
<br><span style='font-size:small;color:#d6e8ff'>{tm} {tick}</span></td></tr></table></td></tr></table>""")
            else:
                out.append(f"""<table width=100% cellspacing=0 cellpadding=0 style='margin:2px 0'><tr>
<td align=left><table cellpadding={pad} style='background:{other_bg}'><tr><td style='color:{txt}'>
<b style='color:{a}'>{html.escape(nick)}</b><br>{body}<br><span style='font-size:small;color:#999'>{tm}</span></td></tr></table></td>
<td width=25%></td></tr></table>""")
        if not out:
            out.append("<p align=center style='color:#999'>Noch keine Nachrichten. Sag hallo! 👋<br>"
                       "Nachrichten an Offline-Kontakte werden zugestellt, sobald sie sich anmelden.</p>")
        self.view.setHtml("".join(out)); self.view.moveCursor(QTextCursor.End)

    # ---- account
    def set_status(self, st):
        self.status_box.setCurrentIndex(["online", "away", "busy", "invisible"].index(st))
        self.conn.send({"t": "status", "status": st})

    def change_password(self):
        if not self.me: return
        old, ok = QInputDialog.getText(self, APP, "Altes Passwort:", QLineEdit.Password)
        if not ok: return
        new, ok = QInputDialog.getText(self, APP, "Neues Passwort (mind. 6 Zeichen):", QLineEdit.Password)
        if not ok: return
        new2, ok = QInputDialog.getText(self, APP, "Neues Passwort wiederholen:", QLineEdit.Password)
        if not ok: return
        if len(new) < 6 or new != new2:
            return QMessageBox.warning(self, APP, "Neues Passwort zu kurz oder nicht identisch.")
        old_auth, _ = derive(old, self.kdf_salt)
        if old_auth != self.auth:
            return QMessageBox.warning(self, APP, "Altes Passwort falsch.")
        salt = nacl.utils.random(argon2id.SALTBYTES)
        auth, vault = derive(new, salt)
        enc = nacl.secret.SecretBox(vault).encrypt(bytes(self.priv))
        self.pw_pending = (salt, auth, vault)
        self.conn.send({"t": "change_password", "old_auth": b64e(old_auth), "salt": b64e(salt), "auth": b64e(auth),
                        "enc_priv": b64e(enc)})

    def change_email(self):
        if not self.me: return
        mail, ok = QInputDialog.getText(self, APP, "Neue E-Mail-Adresse:", text=self.me.get("email", ""))
        if ok and mail.strip():
            self.conn.send({"t": "change_email", "email": mail.strip()})

    def options(self):
        OptionsDialog(self).exec()

    def info(self):
        d = QDialog(self); d.setWindowTitle("Info über Herbstchat"); d.setMinimumWidth(440)
        l = QVBoxLayout(d); l.setContentsMargins(26, 22, 26, 22)
        ic = QLabel(); ic.setPixmap(app_icon(self.settings["accent"]).pixmap(72, 72)); ic.setAlignment(Qt.AlignCenter); l.addWidget(ic)
        t = QLabel(f"{APP} {VERSION}"); t.setObjectName("title"); t.setAlignment(Qt.AlignCenter); l.addWidget(t)
        txt = QLabel(f"""<p align=center>Schön, dass du da bist! 🍂</p>
<p align=center>Herbstchat ist ein kleiner, privater Messenger - gemacht für Freunde, Familie und Bekannte.
Ohne Werbung, ohne Datensammelei und ohne Tracking.</p>
<p align=center>Alle Nachrichten werden auf deinem Gerät verschlüsselt und erst beim Empfänger wieder
entschlüsselt. Nicht einmal der Serverbetreiber kann sie lesen.</p>
<p align=center>Viel Spass beim Chatten - und denk dran: ein nettes Wort kostet nichts.</p>
<p align=center>Besuche meine Webseite:<br><a href="{WEBSITE}" style="font-size:large"><b>herbstleyd.org</b></a></p>
<p align=center style='color:#888'>Herzliche Grüße, Herbstleyd</p>""")
        txt.setWordWrap(True); txt.setOpenExternalLinks(True); l.addWidget(txt)
        b = QPushButton("Schließen"); b.clicked.connect(d.accept); l.addWidget(b)
        d.exec()

    def logout(self):
        self.manual_logout = True; self.reconnect_timer.stop()
        self.save_profile(); self.conn.close()
        self.me = self.auth = self.vault = self.priv = None
        self.contacts = {}; self.current = None; self.pending = {}
        self.profile = {"history": {}, "keys": {}, "unread": {}, "names": {}}
        self.refresh_contacts(); self.render_chat(); self.update_me(); self.set_chat_enabled(False)
        self.hide(); self.show_login()

    def show_login(self):
        dlg = LoginDialog(self)
        if dlg.exec() != QDialog.Accepted and not self.me:
            self.quit()

    def closeEvent(self, e):
        if self.settings["tray"] and self.tray and self.me:
            e.ignore(); self.hide()
            if not getattr(self, "_tray_hint", False):
                self.tray.showMessage(APP, "Herbstchat läuft im Hintergrund weiter.", app_icon(self.settings["accent"]), 3000)
                self._tray_hint = True
        else:
            self.quit()

    def quit(self):
        try: self.save_profile()
        except Exception: pass
        QApplication.quit(); sys.exit(0)


def main():
    if "--selftest" in sys.argv:
        nacl.public.PrivateKey.generate(); derive("selftest", b"0" * 16); print("selftest ok"); sys.exit(0)
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP); app.setQuitOnLastWindowClosed(False)
    from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
    tr = QTranslator(app)
    if tr.load(QLocale("de_DE"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
    if not QSslSocket.supportsSsl():
        QMessageBox.critical(None, APP, "SSL/TLS wird auf diesem System nicht unterstützt (OpenSSL fehlt).")
    w = MainWindow()
    QTimer.singleShot(0, w.show_login)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
