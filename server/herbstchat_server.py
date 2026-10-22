#!/usr/bin/env python3
"""Herbstchat Server - Ende-zu-Ende-verschlüsselter Instant Messenger.

Der Server sieht niemals Klartext-Nachrichten oder Passwörter:
  * Clients leiten aus dem Passwort per Argon2id zwei Schlüssel ab
    (Auth-Schlüssel + Tresor-Schlüssel). Nur der Auth-Schlüssel wird
    gesendet, der Server speichert davon nur einen scrypt-Hash.
  * Der private Schlüssel (X25519) liegt nur mit dem Tresor-Schlüssel
    verschlüsselt auf dem Server.
  * Nachrichten werden clientseitig mit NaCl Box (X25519 + XSalsa20-Poly1305)
    verschlüsselt. Der Server speichert sie nur bis zur Zustellung.
"""
import argparse, asyncio, base64, configparser, getpass, hashlib, hmac, html
import ipaddress, json, logging, os, re, secrets, smtplib, sqlite3, ssl, sys, time
from email.message import EmailMessage
from aiohttp import web, WSMsgType

VERSION = "1.1.0"
DEFAULT_CONF = "/etc/herbstchat/server.conf"
log = logging.getLogger("herbstchat")

NICK_RE = re.compile(r"^[A-Za-z0-9_\-\.]{3,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_MSG = 64 * 1024          # max. Größe verschlüsselter Nachricht
MAX_QUEUE = 2000             # max. offline gespeicherte Nachrichten pro Empfänger
QUEUE_DAYS = 60              # unzugestellte Nachrichten verfallen nach X Tagen


# --------------------------------------------------------------------------- Config
def load_config(path):
    c = configparser.ConfigParser()
    c.read_dict({
        "server": {"host": "0.0.0.0", "port": "47474", "cert": "/etc/herbstchat/cert.pem",
                   "key": "/etc/herbstchat/key.pem", "database": "/var/lib/herbstchat/herbstchat.db",
                   "public_address": "chat.example.org"},
        "admin": {"host": "0.0.0.0", "port": "8088", "user": "admin", "password_hash": "",
                  "allowed_networks": "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fe80::/10,fc00::/7"},
        "smtp": {"host": "", "port": "587", "user": "", "password": "", "sender": "", "starttls": "yes"},
    })
    c.read(path)
    return c


def hash_admin_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + salt.hex() + "$" + h.hex()


def check_admin_pw(pw, stored):
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(s), n=2**14, r=8, p=1)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


# --------------------------------------------------------------------------- DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nick TEXT UNIQUE COLLATE NOCASE NOT NULL,
  email TEXT NOT NULL,
  kdf_salt TEXT NOT NULL,
  auth_salt TEXT NOT NULL,
  auth_hash TEXT NOT NULL,
  pubkey TEXT NOT NULL,
  enc_priv TEXT NOT NULL,
  created REAL NOT NULL,
  last_login REAL, last_ip TEXT,
  banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '',
  timeout_until REAL DEFAULT 0, timeout_reason TEXT DEFAULT '',
  muted INTEGER DEFAULT 0,
  note TEXT DEFAULT '',
  msg_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS contacts(owner INTEGER, contact INTEGER, PRIMARY KEY(owner, contact));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT, sender INTEGER,
  recipient INTEGER, payload TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS idx_msg_rcpt ON messages(recipient);
CREATE TABLE IF NOT EXISTS auditlog(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, text TEXT);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL, contact_id INTEGER NOT NULL,
  blob TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id);
"""


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.c = sqlite3.connect(path, isolation_level=None)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.executescript(SCHEMA)
        r = self.one("SELECT v FROM meta WHERE k='secret'")
        if not r:
            self.x("INSERT INTO meta VALUES('secret',?)", (secrets.token_hex(32),))
            r = self.one("SELECT v FROM meta WHERE k='secret'")
        self.secret = bytes.fromhex(r["v"])

    def x(self, q, a=()):
        return self.c.execute(q, a)

    def one(self, q, a=()):
        return self.c.execute(q, a).fetchone()

    def all(self, q, a=()):
        return self.c.execute(q, a).fetchall()

    def audit(self, text):
        self.x("INSERT INTO auditlog(ts,text) VALUES(?,?)", (time.time(), text))
        log.info("AUDIT %s", text)


# --------------------------------------------------------------------------- Chat server
class ChatServer:
    def __init__(self, cfg, db):
        self.cfg, self.db = cfg, db
        self.online = {}       # user_id -> set(ws)
        self.status = {}       # user_id -> "online"/"away"/"busy"/"invisible"
        self.started = time.time()
        self.fails = {}        # ip -> [timestamps]

    # ---- helpers
    @staticmethod
    async def send(ws, obj):
        try:
            await ws.send_str(json.dumps(obj))
        except Exception:
            pass

    async def send_user(self, uid, obj):
        for ws in list(self.online.get(uid, ())):
            await self.send(ws, obj)

    def visible_status(self, uid):
        if uid not in self.online:
            return "offline"
        s = self.status.get(uid, "online")
        return "offline" if s == "invisible" else s

    async def broadcast_presence(self, uid):
        st = self.visible_status(uid)
        for r in self.db.all("SELECT owner FROM contacts WHERE contact=?", (uid,)):
            if r["owner"] in self.online:
                await self.send_user(r["owner"], {"t": "presence", "id": uid, "status": st})

    def contact_obj(self, row):
        return {"id": row["id"], "nick": row["nick"], "pubkey": row["pubkey"],
                "status": self.visible_status(row["id"])}

    async def kick(self, uid, reason):
        for ws in list(self.online.get(uid, ())):
            await self.send(ws, {"t": "kicked", "reason": reason})
            await ws.close()

    def blocked(self, ip):
        now = time.time()
        lst = [t for t in self.fails.get(ip, []) if now - t < 600]
        self.fails[ip] = lst
        return len(lst) >= 10

    def user_lock_reason(self, u):
        if u["banned"]:
            return "Dein Account wurde gesperrt. " + (u["ban_reason"] or "")
        if u["timeout_until"] and u["timeout_until"] > time.time():
            until = time.strftime("%d.%m.%Y %H:%M", time.localtime(u["timeout_until"]))
            return f"Dein Account ist bis {until} pausiert (Timeout). " + (u["timeout_reason"] or "")
        return None

    # ---- websocket
    async def ws_handler(self, request):
        ws = web.WebSocketResponse(heartbeat=30, max_msg_size=MAX_MSG * 2)
        await ws.prepare(request)
        ip = request.remote or "?"
        uid = None
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    d = json.loads(m.data)
                    t = d.get("t")
                except Exception:
                    continue
                if uid is None:
                    uid = await self.handle_unauth(ws, ip, t, d)
                    continue
                await self.handle_auth(ws, uid, t, d)
        finally:
            if uid is not None:
                s = self.online.get(uid)
                if s:
                    s.discard(ws)
                    if not s:
                        del self.online[uid]
                        self.status.pop(uid, None)
                        await self.broadcast_presence(uid)
        return ws

    async def handle_unauth(self, ws, ip, t, d):
        db = self.db
        if t == "hello":
            await self.send(ws, {"t": "hello", "server": "Herbstchat", "version": VERSION})
        elif t == "prelogin":
            nick = str(d.get("nick", ""))
            u = db.one("SELECT kdf_salt FROM users WHERE nick=?", (nick,))
            # für unbekannte Nicks deterministisches Fake-Salt (keine User-Enumeration)
            salt = u["kdf_salt"] if u else base64.b64encode(
                hmac.new(db.secret, nick.lower().encode(), "sha256").digest()[:16]).decode()
            await self.send(ws, {"t": "salt", "salt": salt})
        elif t == "register":
            nick, email = str(d.get("nick", "")).strip(), str(d.get("email", "")).strip()
            err = None
            if not NICK_RE.match(nick):
                err = "Nickname: 3-24 Zeichen, nur Buchstaben, Zahlen, _ - ."
            elif not EMAIL_RE.match(email) or len(email) > 200:
                err = "Bitte eine gültige E-Mail-Adresse angeben."
            elif db.one("SELECT 1 FROM users WHERE nick=?", (nick,)):
                err = "Dieser Nickname ist bereits vergeben."
            elif db.one("SELECT 1 FROM meta WHERE k='reg_closed' AND v='1'"):
                err = "Registrierungen sind derzeit geschlossen."
            if not err:
                try:
                    auth = base64.b64decode(d["auth"])
                    base64.b64decode(d["salt"]); base64.b64decode(d["pubkey"]); base64.b64decode(d["enc_priv"])
                    assert len(auth) == 32
                except Exception:
                    err = "Ungültige Registrierungsdaten."
            if err:
                await self.send(ws, {"t": "error", "ctx": "register", "msg": err})
                return None
            asalt = secrets.token_bytes(16)
            ah = hashlib.scrypt(auth, salt=asalt, n=2**14, r=8, p=1)
            db.x("INSERT INTO users(nick,email,kdf_salt,auth_salt,auth_hash,pubkey,enc_priv,created) "
                 "VALUES(?,?,?,?,?,?,?,?)", (nick, email, d["salt"], asalt.hex(), ah.hex(),
                                             d["pubkey"], d["enc_priv"], time.time()))
            db.audit(f"Registrierung: {nick} <{email}> von {ip}")
            await self.send(ws, {"t": "register_ok"})
        elif t == "login":
            if self.blocked(ip):
                await self.send(ws, {"t": "error", "ctx": "login", "msg": "Zu viele Fehlversuche. Bitte 10 Minuten warten."})
                return None
            u = db.one("SELECT * FROM users WHERE nick=?", (str(d.get("nick", "")),))
            ok = False
            if u:
                try:
                    calc = hashlib.scrypt(base64.b64decode(d.get("auth", "")), salt=bytes.fromhex(u["auth_salt"]),
                                          n=2**14, r=8, p=1)
                    ok = hmac.compare_digest(calc.hex(), u["auth_hash"])
                except Exception:
                    ok = False
            if not ok:
                self.fails.setdefault(ip, []).append(time.time())
                await self.send(ws, {"t": "error", "ctx": "login", "msg": "Nickname oder Passwort falsch."})
                return None
            reason = self.user_lock_reason(u)
            if reason:
                await self.send(ws, {"t": "error", "ctx": "login", "msg": reason})
                return None
            uid = u["id"]
            db.x("UPDATE users SET last_login=?, last_ip=? WHERE id=?", (time.time(), ip, uid))
            self.online.setdefault(uid, set()).add(ws)
            st = d.get("status", "online")
            self.status[uid] = st if st in ("online", "away", "busy", "invisible") else "online"
            contacts = [self.contact_obj(r) for r in db.all(
                "SELECT u.* FROM contacts c JOIN users u ON u.id=c.contact WHERE c.owner=? ORDER BY u.nick", (uid,))]
            motd = db.one("SELECT v FROM meta WHERE k='motd'")
            hcnt = db.one("SELECT COALESCE(MAX(id),0) FROM history")["MAX(id)"]
            await self.send(ws, {"t": "login_ok", "id": uid, "nick": u["nick"], "email": u["email"],
                                  "pubkey": u["pubkey"], "enc_priv": u["enc_priv"], "contacts": contacts,
                                  "motd": motd["v"] if motd else "", "history_counter": hcnt})
            await self.broadcast_presence(uid)
            for r in db.all("SELECT m.*, u.nick, u.pubkey FROM messages m LEFT JOIN users u ON u.id=m.sender "
                            "WHERE recipient=? ORDER BY m.id", (uid,)):
                await self.send(ws, {"t": "msg", "id": r["id"], "from": r["sender"], "from_nick": r["nick"],
                                     "from_pubkey": r["pubkey"], "payload": r["payload"], "ts": r["ts"]})
            return uid
        return None

    async def handle_auth(self, ws, uid, t, d):
        db = self.db
        u = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            await self.send(ws, {"t": "kicked", "reason": "Account existiert nicht mehr."})
            await ws.close(); return
        if t == "msg":
            reason = self.user_lock_reason(u)
            if reason or u["muted"]:
                await self.send(ws, {"t": "error", "ctx": "msg", "cid": d.get("cid"),
                                     "msg": reason or "Du wurdest stummgeschaltet und kannst keine Nachrichten senden."})
                return
            payload = str(d.get("payload", ""))
            try:
                to = int(d.get("to"))
            except Exception:
                return
            if len(payload) > MAX_MSG:
                await self.send(ws, {"t": "error", "ctx": "msg", "cid": d.get("cid"), "msg": "Nachricht zu groß."}); return
            if not db.one("SELECT 1 FROM users WHERE id=?", (to,)):
                await self.send(ws, {"t": "error", "ctx": "msg", "cid": d.get("cid"), "msg": "Empfänger existiert nicht."}); return
            if db.one("SELECT COUNT(*) n FROM messages WHERE recipient=?", (to,))["n"] >= MAX_QUEUE:
                await self.send(ws, {"t": "error", "ctx": "msg", "cid": d.get("cid"), "msg": "Postfach des Empfängers ist voll."}); return
            now = time.time()
            cur = db.x("INSERT INTO messages(sender,recipient,payload,ts) VALUES(?,?,?,?)", (uid, to, payload, now))
            db.x("UPDATE users SET msg_count=msg_count+1 WHERE id=?", (uid,))
            db.x("INSERT INTO history(user_id, contact_id, blob, ts) VALUES(?,?,?,?)", (to, uid, payload, now))
            mid = cur.lastrowid
            # Absender automatisch beim Empfänger als Kontakt "bekannt machen"
            await self.send_user(to, {"t": "msg", "id": mid, "from": uid, "from_nick": u["nick"],
                                      "from_pubkey": u["pubkey"], "payload": payload, "ts": now})
            await self.send(ws, {"t": "sent", "cid": d.get("cid"), "id": mid, "ts": now,
                                 "queued": to not in self.online})
        elif t == "ack":
            ids = [int(i) for i in d.get("ids", []) if str(i).isdigit()][:500]
            for i in ids:
                db.x("DELETE FROM messages WHERE id=? AND recipient=?", (i, uid))
        elif t == "typing":
            try:
                await self.send_user(int(d.get("to")), {"t": "typing", "from": uid})
            except Exception:
                pass
        elif t == "search":
            q = str(d.get("q", ""))[:24]
            rows = db.all("SELECT * FROM users WHERE nick LIKE ? AND id<>? AND banned=0 ORDER BY nick LIMIT 20",
                          (q.replace("%", "") + "%", uid))
            await self.send(ws, {"t": "search", "results": [{"id": r["id"], "nick": r["nick"]} for r in rows]})
        elif t == "add_contact":
            r = db.one("SELECT * FROM users WHERE (id=? OR nick=?) AND id<>?",
                       (d.get("id", -1), str(d.get("nick", "")), uid))
            if not r:
                await self.send(ws, {"t": "error", "ctx": "contact", "msg": "Benutzer nicht gefunden."}); return
            db.x("INSERT OR IGNORE INTO contacts VALUES(?,?)", (uid, r["id"]))
            await self.send(ws, {"t": "contact", "contact": self.contact_obj(r)})
        elif t == "remove_contact":
            db.x("DELETE FROM contacts WHERE owner=? AND contact=?", (uid, d.get("id")))
            await self.send(ws, {"t": "contact_removed", "id": d.get("id")})
        elif t == "get_user":
            r = db.one("SELECT * FROM users WHERE id=?", (d.get("id"),))
            if r:
                await self.send(ws, {"t": "user", "user": self.contact_obj(r)})
        elif t == "status":
            st = d.get("status")
            if st in ("online", "away", "busy", "invisible"):
                self.status[uid] = st
                await self.broadcast_presence(uid)
        elif t == "change_password":
            try:
                calc = hashlib.scrypt(base64.b64decode(d["old_auth"]), salt=bytes.fromhex(u["auth_salt"]), n=2**14, r=8, p=1)
                assert hmac.compare_digest(calc.hex(), u["auth_hash"])
                new_auth = base64.b64decode(d["auth"]); assert len(new_auth) == 32
                base64.b64decode(d["salt"]); base64.b64decode(d["enc_priv"])
            except Exception:
                await self.send(ws, {"t": "error", "ctx": "password", "msg": "Altes Passwort falsch."}); return
            asalt = secrets.token_bytes(16)
            ah = hashlib.scrypt(new_auth, salt=asalt, n=2**14, r=8, p=1)
            db.x("UPDATE users SET kdf_salt=?,auth_salt=?,auth_hash=?,enc_priv=? WHERE id=?",
                 (d["salt"], asalt.hex(), ah.hex(), d["enc_priv"], uid))
            db.audit(f"Passwort geändert: {u['nick']}")
            await self.send(ws, {"t": "password_ok"})
        elif t == "change_email":
            email = str(d.get("email", "")).strip()
            if not EMAIL_RE.match(email):
                await self.send(ws, {"t": "error", "ctx": "email", "msg": "Ungültige E-Mail-Adresse."}); return
            db.x("UPDATE users SET email=? WHERE id=?", (email, uid))
            await self.send(ws, {"t": "email_ok", "email": email})
        elif t == "history_counter":
            cnt = db.one("SELECT COALESCE(MAX(id),0) FROM history")["MAX(id)"]
            await self.send(ws, {"t": "history_counter", "counter": cnt})
        elif t == "history_delta":
            since = int(d.get("since", 0))
            rows = db.all("SELECT * FROM history WHERE user_id=? AND id>? ORDER BY id", (uid, since))
            await self.send(ws, {"t": "history_delta", "delta": [{"id": r["id"], "contact_id": r["contact_id"],
                          "blob": r["blob"], "ts": r["ts"]} for r in rows]})
        elif t == "history_upload":
            for entry in d.get("entries", []):
                try:
                    cid = int(entry["contact_id"])
                    blob = str(entry["blob"])[:65536]
                    ts = float(entry.get("ts", time.time()))
                    assert db.one("SELECT 1 FROM users WHERE id=?", (cid,))
                except (ValueError, KeyError, AssertionError):
                    continue
                db.x("INSERT INTO history(user_id, contact_id, blob, ts) VALUES(?,?,?,?)",
                     (uid, cid, blob, ts))
            await self.send(ws, {"t": "history_uploaded"})
        elif t == "history_updated":
            cnt = int(d.get("counter", 0))
            cur = db.one("SELECT COALESCE(MAX(id),0) FROM history")["MAX(id)"]
            await self.send(ws, {"t": "history_updated_ok", "counter": cur})
        elif t == "ping":
            await self.send(ws, {"t": "pong"})

    async def cleanup_loop(self):
        while True:
            try:
                self.db.x("DELETE FROM messages WHERE ts<?", (time.time() - QUEUE_DAYS * 86400,))
            except Exception as e:
                log.warning("cleanup: %s", e)
            await asyncio.sleep(3600)


# --------------------------------------------------------------------------- Admin web
CSS = """
body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f4f1ec;color:#2b2b2b}
header{background:linear-gradient(90deg,#b5541c,#d98c2b);color:#fff;padding:14px 24px;display:flex;gap:24px;align-items:center}
header a{color:#fff;text-decoration:none;font-weight:500}header h1{margin:0;font-size:20px;margin-right:auto}
main{padding:24px;max-width:1300px;margin:auto}
.card{background:#fff;border-radius:10px;padding:18px;margin-bottom:18px;box-shadow:0 1px 3px #0002}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid #eee;text-align:left}
th{background:#faf6f0}tr:hover td{background:#fffaf3}
.b{display:inline-block;padding:2px 8px;border-radius:9px;font-size:12px;color:#fff}
.on{background:#3a9b4c}.off{background:#999}.ban{background:#c0392b}.to{background:#e67e22}.mu{background:#8e44ad}
input,select,textarea,button{font:inherit;padding:6px 9px;border:1px solid #ccc;border-radius:6px}
button{background:#b5541c;color:#fff;border:none;cursor:pointer}button.sec{background:#777}button.danger{background:#c0392b}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}
.stat{font-size:28px;font-weight:700;color:#b5541c}form.inline{display:inline}
.flash{background:#e8f6ea;border-left:4px solid #3a9b4c;padding:10px;margin-bottom:14px}
"""


class AdminSite:
    def __init__(self, cfg, db, chat):
        self.cfg, self.db, self.chat = cfg, db, chat
        self.nets = [ipaddress.ip_network(n.strip(), strict=False)
                     for n in cfg["admin"]["allowed_networks"].split(",") if n.strip()]
        self.csrf = secrets.token_hex(16)

    @web.middleware
    async def guard(self, request, handler):
        try:
            ip = ipaddress.ip_address((request.remote or "").split("%")[0])
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            allowed = any(ip in n for n in self.nets)
        except ValueError:
            allowed = False
        if not allowed:
            return web.Response(status=403, text="Zugriff nur aus dem lokalen Netz erlaubt.")
        auth = request.headers.get("Authorization", "")
        ok = False
        if auth.startswith("Basic "):
            try:
                user, pw = base64.b64decode(auth[6:]).decode().split(":", 1)
                ok = user == self.cfg["admin"]["user"] and check_admin_pw(pw, self.cfg["admin"]["password_hash"])
            except Exception:
                ok = False
        if not ok:
            return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="Herbstchat Admin"'},
                                text="Anmeldung erforderlich")
        if request.method == "POST":
            data = await request.post()
            if data.get("csrf") != self.csrf:
                return web.Response(status=400, text="Ungültiges Formular (CSRF).")
        return await handler(request)

    def page(self, title, body, flash=""):
        f = f'<div class="flash">{html.escape(flash)}</div>' if flash else ""
        return web.Response(content_type="text/html", text=f"""<!doctype html><html lang=de><head>
<meta charset=utf-8><title>{html.escape(title)} - Herbstchat Admin</title><style>{CSS}</style></head><body>
<header><h1>Herbstchat Admin</h1><a href="/">Dashboard</a><a href="/users">Benutzer</a>
<a href="/broadcast">Rundschreiben</a><a href="/settings">Einstellungen</a><a href="/log">Protokoll</a></header>
<main>{f}{body}</main></body></html>""")

    def hid(self):
        return f'<input type=hidden name=csrf value="{self.csrf}">'

    @staticmethod
    def ft(ts):
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts else "-"

    def badges(self, u):
        b = []
        b.append('<span class="b on">online</span>' if u["id"] in self.chat.online else '<span class="b off">offline</span>')
        if u["banned"]: b.append('<span class="b ban">gebannt</span>')
        if u["timeout_until"] and u["timeout_until"] > time.time(): b.append('<span class="b to">Timeout</span>')
        if u["muted"]: b.append('<span class="b mu">stumm</span>')
        return " ".join(b)

    async def dashboard(self, request):
        db = self.db
        n = db.one("SELECT COUNT(*) n FROM users")["n"]
        banned = db.one("SELECT COUNT(*) n FROM users WHERE banned=1")["n"]
        to = db.one("SELECT COUNT(*) n FROM users WHERE timeout_until>?", (time.time(),))["n"]
        q = db.one("SELECT COUNT(*) n FROM messages")["n"]
        new7 = db.one("SELECT COUNT(*) n FROM users WHERE created>?", (time.time() - 7 * 86400,))["n"]
        act = db.one("SELECT COUNT(*) n FROM users WHERE last_login>?", (time.time() - 86400,))["n"]
        up = int(time.time() - self.chat.started)
        dbsize = os.path.getsize(self.cfg["server"]["database"]) // 1024 if os.path.exists(self.cfg["server"]["database"]) else 0
        stats = [("Benutzer", n), ("Online", len(self.chat.online)), ("Aktiv (24h)", act), ("Neu (7 Tage)", new7),
                 ("Gebannt", banned), ("Im Timeout", to), ("Offline-Nachrichten", q),
                 ("Uptime", f"{up//86400}d {up%86400//3600}h {up%3600//60}m"), ("DB-Größe", f"{dbsize} KB")]
        cards = "".join(f'<div class=card><div>{k}</div><div class=stat>{v}</div></div>' for k, v in stats)
        recent = "".join(f"<tr><td>{self.ft(r['ts'])}</td><td>{html.escape(r['text'])}</td></tr>"
                         for r in db.all("SELECT * FROM auditlog ORDER BY id DESC LIMIT 10"))
        return self.page("Dashboard", f"""<div class=grid>{cards}</div>
<div class=card><h3>Letzte Ereignisse</h3><table>{recent}</table></div>
<div class=card>Server-Adresse für Clients: <b>{html.escape(self.cfg['server']['public_address'])}:{self.cfg['server']['port']}</b>
&nbsp;|&nbsp; Version {VERSION}</div>""", request.query.get("m", ""))

    async def users(self, request):
        q = request.query.get("q", "")
        flt = request.query.get("f", "")
        sql, args = "SELECT * FROM users WHERE (nick LIKE ? OR email LIKE ?)", [f"%{q}%", f"%{q}%"]
        if flt == "banned": sql += " AND banned=1"
        if flt == "timeout": sql += f" AND timeout_until>{time.time()}"
        if flt == "online": sql += " AND id IN (%s)" % (",".join(map(str, self.chat.online)) or "-1")
        if flt == "inactive": sql += f" AND (last_login IS NULL OR last_login<{time.time()-90*86400})"
        sort = {"nick": "nick", "created": "created DESC", "login": "last_login DESC", "msgs": "msg_count DESC"}.get(
            request.query.get("s", ""), "nick")
        rows = self.db.all(sql + " ORDER BY " + sort, args)
        tr = "".join(f"""<tr><td>{u['id']}</td><td><a href="/user/{u['id']}">{html.escape(u['nick'])}</a></td>
<td>{html.escape(u['email'])}</td><td>{self.badges(u)}</td><td>{self.ft(u['created'])}</td>
<td>{self.ft(u['last_login'])}</td><td>{u['msg_count']}</td></tr>""" for u in rows)
        opts = "".join(f'<option value="{v}" {"selected" if flt==v else ""}>{l}</option>' for v, l in
                       [("", "Alle"), ("online", "Online"), ("banned", "Gebannt"), ("timeout", "Im Timeout"),
                        ("inactive", "Inaktiv >90 Tage")])
        return self.page("Benutzer", f"""<div class=card><form>
<input name=q placeholder="Nick oder E-Mail" value="{html.escape(q)}"> <select name=f>{opts}</select>
<select name=s><option value=nick>Sortierung: Nick</option><option value=created>Neueste</option>
<option value=login>Letzter Login</option><option value=msgs>Meiste Nachrichten</option></select>
<button>Suchen</button> <a href="/export.csv">E-Mail-Liste als CSV exportieren</a></form></div>
<div class=card><b>{len(rows)}</b> Benutzer<table><tr><th>ID</th><th>Nickname</th><th>E-Mail</th><th>Status</th>
<th>Registriert</th><th>Letzter Login</th><th>Nachr.</th></tr>{tr}</table></div>""", request.query.get("m", ""))

    async def user(self, request):
        uid = int(request.match_info["id"])
        u = self.db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            raise web.HTTPFound("/users?m=Benutzer+nicht+gefunden")
        h, a = self.hid(), f"/user/{uid}/action"
        nc = self.db.one("SELECT COUNT(*) n FROM contacts WHERE owner=?", (uid,))["n"]
        q = self.db.one("SELECT COUNT(*) n FROM messages WHERE recipient=?", (uid,))["n"]
        to_opts = "".join(f'<option value="{s}">{l}</option>' for s, l in [
            (6*3600, "6 Stunden"), (12*3600, "12 Stunden"), (86400, "1 Tag"), (2*86400, "2 Tage"), (3*86400, "3 Tage"),
            (7*86400, "7 Tage"), (14*86400, "14 Tage"), (30*86400, "30 Tage")])
        tou = self.ft(u["timeout_until"]) if u["timeout_until"] and u["timeout_until"] > time.time() else "-"
        fp = hashlib.sha256(base64.b64decode(u["pubkey"])).hexdigest()[:32]
        fp = " ".join(fp[i:i+4] for i in range(0, 32, 4))
        body = f"""<div class=card><h2>{html.escape(u['nick'])} {self.badges(u)}</h2><table>
<tr><th>ID</th><td>{u['id']}</td></tr><tr><th>E-Mail</th><td><a href="mailto:{html.escape(u['email'])}">{html.escape(u['email'])}</a></td></tr>
<tr><th>Registriert</th><td>{self.ft(u['created'])}</td></tr><tr><th>Letzter Login</th><td>{self.ft(u['last_login'])} von {html.escape(u['last_ip'] or '-')}</td></tr>
<tr><th>Gesendete Nachrichten</th><td>{u['msg_count']}</td></tr><tr><th>Kontakte</th><td>{nc}</td></tr>
<tr><th>Wartende Offline-Nachrichten</th><td>{q}</td></tr><tr><th>Schlüssel-Fingerabdruck</th><td><code>{fp}</code></td></tr>
<tr><th>Timeout bis</th><td>{tou} {html.escape(u['timeout_reason'] or '')}</td></tr>
<tr><th>Bann-Grund</th><td>{html.escape(u['ban_reason'] or '-')}</td></tr></table></div>
<div class=grid style="grid-template-columns:repeat(auto-fit,minmax(380px,1fr))">
<div class=card><h3>Nickname ändern</h3><form method=post action="{a}">{h}<input type=hidden name=do value=rename>
<input name=nick value="{html.escape(u['nick'])}" required> <button>Speichern</button></form>
<h3>E-Mail ändern</h3><form method=post action="{a}">{h}<input type=hidden name=do value=email>
<input name=email type=email value="{html.escape(u['email'])}" required> <button>Speichern</button></form></div>
<div class=card><h3>Timeout</h3><form method=post action="{a}">{h}<input type=hidden name=do value=timeout>
<select name=secs>{to_opts}</select> <input name=reason placeholder="Grund (optional)"> <button>Timeout setzen</button></form>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=untimeout><button class=sec>Timeout aufheben</button></form></div>
<div class=card><h3>Bann</h3><form method=post action="{a}">{h}<input type=hidden name=do value=ban>
<input name=reason placeholder="Grund (optional)"> <button class=danger>Bannen</button></form>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=unban><button class=sec>Entbannen</button></form></div>
<div class=card><h3>Stummschalten / Verbindung</h3><p>Stumm: User kann sich einloggen und lesen, aber nichts senden.</p>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=mute><button>Stummschalten</button></form>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=unmute><button class=sec>Aufheben</button></form>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=kick><button class=sec>Verbindung trennen</button></form></div>
<div class=card><h3>Systemnachricht an diesen User</h3><form method=post action="{a}">{h}<input type=hidden name=do value=notice>
<textarea name=text rows=3 style="width:95%" required></textarea><br><label><input type=checkbox name=mail value=1> zusätzlich per E-Mail</label>
<button>Senden</button></form></div>
<div class=card><h3>Admin-Notiz (nur intern)</h3><form method=post action="{a}">{h}<input type=hidden name=do value=note>
<textarea name=note rows=3 style="width:95%">{html.escape(u['note'] or '')}</textarea><br><button>Speichern</button></form></div>
<div class=card><h3>Gefahrenzone</h3>
<form method=post action="{a}" class=inline>{h}<input type=hidden name=do value=purge><button class=sec>Offline-Nachrichten verwerfen</button></form>
<form method=post action="{a}" class=inline onsubmit="return confirm('Account wirklich endgültig löschen?')">{h}
<input type=hidden name=do value=delete><button class=danger>Account löschen</button></form></div></div>"""
        return self.page(u["nick"], body, request.query.get("m", ""))

    async def user_action(self, request):
        uid = int(request.match_info["id"])
        d = await request.post()
        db, chat = self.db, self.chat
        u = db.one("SELECT * FROM users WHERE id=?", (uid,))
        if not u:
            raise web.HTTPFound("/users")
        do, msg = d.get("do"), "Gespeichert."
        if do == "rename":
            nick = d.get("nick", "").strip()
            if not NICK_RE.match(nick):
                msg = "Ungültiger Nickname."
            elif db.one("SELECT 1 FROM users WHERE nick=? AND id<>?", (nick, uid)):
                msg = "Nickname bereits vergeben."
            else:
                db.x("UPDATE users SET nick=? WHERE id=?", (nick, uid))
                db.audit(f"Admin: {u['nick']} umbenannt in {nick}")
                for r in db.all("SELECT owner FROM contacts WHERE contact=?", (uid,)):
                    await chat.send_user(r["owner"], {"t": "renamed", "id": uid, "nick": nick})
                await chat.send_user(uid, {"t": "renamed", "id": uid, "nick": nick, "self": True})
                msg = "Nickname geändert."
        elif do == "email":
            if EMAIL_RE.match(d.get("email", "")):
                db.x("UPDATE users SET email=? WHERE id=?", (d["email"].strip(), uid)); db.audit(f"Admin: E-Mail von {u['nick']} geändert")
            else:
                msg = "Ungültige E-Mail."
        elif do == "timeout":
            secs = max(6 * 3600, min(30 * 86400, int(d.get("secs", 21600))))
            db.x("UPDATE users SET timeout_until=?, timeout_reason=? WHERE id=?", (time.time() + secs, d.get("reason", ""), uid))
            db.audit(f"Admin: Timeout {secs//3600}h für {u['nick']}")
            await chat.kick(uid, f"Du wurdest für {secs//3600} Stunden in ein Timeout geschickt. {d.get('reason','')}")
            msg = "Timeout gesetzt."
        elif do == "untimeout":
            db.x("UPDATE users SET timeout_until=0 WHERE id=?", (uid,)); db.audit(f"Admin: Timeout aufgehoben für {u['nick']}")
        elif do == "ban":
            db.x("UPDATE users SET banned=1, ban_reason=? WHERE id=?", (d.get("reason", ""), uid))
            db.audit(f"Admin: {u['nick']} gebannt")
            await chat.kick(uid, "Dein Account wurde gesperrt. " + d.get("reason", ""))
            msg = "Gebannt."
        elif do == "unban":
            db.x("UPDATE users SET banned=0, ban_reason='' WHERE id=?", (uid,)); db.audit(f"Admin: {u['nick']} entbannt")
        elif do == "mute":
            db.x("UPDATE users SET muted=1 WHERE id=?", (uid,)); db.audit(f"Admin: {u['nick']} stumm")
        elif do == "unmute":
            db.x("UPDATE users SET muted=0 WHERE id=?", (uid,))
        elif do == "kick":
            await chat.kick(uid, "Die Verbindung wurde vom Administrator getrennt."); msg = "Getrennt."
        elif do == "notice":
            await chat.send_user(uid, {"t": "notice", "text": d.get("text", "")})
            if d.get("mail"):
                msg = send_mails(self.cfg, [u["email"]], "Herbstchat - Nachricht vom Administrator", d.get("text", ""))
            else:
                msg = "Systemnachricht gesendet."
        elif do == "note":
            db.x("UPDATE users SET note=? WHERE id=?", (d.get("note", ""), uid))
        elif do == "purge":
            db.x("DELETE FROM messages WHERE recipient=?", (uid,)); msg = "Offline-Nachrichten verworfen."
        elif do == "delete":
            await chat.kick(uid, "Dein Account wurde gelöscht.")
            db.x("DELETE FROM messages WHERE recipient=? OR sender=?", (uid, uid))
            db.x("DELETE FROM contacts WHERE owner=? OR contact=?", (uid, uid))
            db.x("DELETE FROM users WHERE id=?", (uid,))
            db.audit(f"Admin: Account {u['nick']} <{u['email']}> gelöscht")
            raise web.HTTPFound("/users?m=Account+gelöscht")
        raise web.HTTPFound(f"/user/{uid}?m=" + msg.replace(" ", "+"))

    async def export(self, request):
        lines = ["id;nick;email;registriert;letzter_login;status"]
        for u in self.db.all("SELECT * FROM users ORDER BY nick"):
            st = "gebannt" if u["banned"] else "aktiv"
            lines.append(f"{u['id']};{u['nick']};{u['email']};{self.ft(u['created'])};{self.ft(u['last_login'])};{st}")
        return web.Response(text="\n".join(lines), content_type="text/csv",
                            headers={"Content-Disposition": "attachment; filename=herbstchat-users.csv"})

    async def broadcast(self, request):
        h = self.hid()
        return self.page("Rundschreiben", f"""<div class=card><h3>Rundschreiben / Wartungsankündigung</h3>
<form method=post action="/broadcast">{h}<p><input name=subject value="Herbstchat - Wartungsarbeiten" style="width:60%"></p>
<textarea name=text rows=8 style="width:95%" placeholder="z.B. Am Samstag ab 20 Uhr ist der Server für ca. 1 Stunde nicht erreichbar." required></textarea>
<p><label><input type=checkbox name=inapp value=1 checked> als Systemnachricht an alle Online-User</label><br>
<label><input type=checkbox name=mail value=1> per E-Mail an alle User (SMTP muss in server.conf eingerichtet sein)</label><br>
<label><input type=checkbox name=excl_banned value=1 checked> gebannte User ausschließen</label></p><button>Senden</button></form></div>""",
                         request.query.get("m", ""))

    async def broadcast_post(self, request):
        d = await request.post()
        text, msg = d.get("text", ""), []
        if d.get("inapp"):
            for uid in list(self.chat.online):
                await self.chat.send_user(uid, {"t": "notice", "text": text})
            msg.append(f"Systemnachricht an {len(self.chat.online)} Online-User gesendet.")
        if d.get("mail"):
            q = "SELECT email FROM users" + (" WHERE banned=0" if d.get("excl_banned") else "")
            msg.append(send_mails(self.cfg, [r["email"] for r in self.db.all(q)], d.get("subject", "Herbstchat"), text))
        self.db.audit("Admin: Rundschreiben versendet")
        raise web.HTTPFound("/broadcast?m=" + " ".join(msg).replace(" ", "+"))

    async def settings(self, request):
        h = self.hid()
        motd = self.db.one("SELECT v FROM meta WHERE k='motd'")
        closed = self.db.one("SELECT v FROM meta WHERE k='reg_closed'")
        closed = closed and closed["v"] == "1"
        return self.page("Einstellungen", f"""<div class=card><h3>Nachricht des Tages (wird beim Login angezeigt)</h3>
<form method=post action="/settings">{h}<input type=hidden name=do value=motd><textarea name=motd rows=3 style="width:95%">{html.escape(motd['v'] if motd else '')}</textarea><br><button>Speichern</button></form></div>
<div class=card><h3>Registrierung</h3><form method=post action="/settings">{h}<input type=hidden name=do value=reg>
<label><input type=checkbox name=closed value=1 {"checked" if closed else ""}> Neue Registrierungen sperren</label> <button>Speichern</button></form></div>
<div class=card><h3>Test-E-Mail</h3><form method=post action="/settings">{h}<input type=hidden name=do value=mailtest>
<input name=to type=email placeholder="deine@adresse.de" required> <button>Senden</button></form></div>
<div class=card><h3>Wartung</h3><form method=post action="/settings">{h}<input type=hidden name=do value=vacuum><button class=sec>Datenbank optimieren (VACUUM)</button></form></div>""",
                         request.query.get("m", ""))

    async def settings_post(self, request):
        d = await request.post()
        msg = "Gespeichert."
        if d.get("do") == "motd":
            self.db.x("INSERT OR REPLACE INTO meta VALUES('motd',?)", (d.get("motd", ""),))
        elif d.get("do") == "reg":
            self.db.x("INSERT OR REPLACE INTO meta VALUES('reg_closed',?)", ("1" if d.get("closed") else "0",))
        elif d.get("do") == "mailtest":
            msg = send_mails(self.cfg, [d.get("to")], "Herbstchat Test", "Dies ist eine Test-E-Mail vom Herbstchat-Server.")
        elif d.get("do") == "vacuum":
            self.db.x("VACUUM"); msg = "Datenbank optimiert."
        raise web.HTTPFound("/settings?m=" + msg.replace(" ", "+"))

    async def logpage(self, request):
        tr = "".join(f"<tr><td>{self.ft(r['ts'])}</td><td>{html.escape(r['text'])}</td></tr>"
                     for r in self.db.all("SELECT * FROM auditlog ORDER BY id DESC LIMIT 500"))
        return self.page("Protokoll", f"<div class=card><h3>Protokoll (letzte 500)</h3><table>{tr}</table></div>")

    def app(self):
        a = web.Application(middlewares=[self.guard])
        a.add_routes([web.get("/", self.dashboard), web.get("/users", self.users), web.get("/user/{id}", self.user),
                      web.post("/user/{id}/action", self.user_action), web.get("/export.csv", self.export),
                      web.get("/broadcast", self.broadcast), web.post("/broadcast", self.broadcast_post),
                      web.get("/settings", self.settings), web.post("/settings", self.settings_post),
                      web.get("/log", self.logpage)])
        return a


def send_mails(cfg, recipients, subject, text):
    s = cfg["smtp"]
    if not s["host"]:
        return "SMTP ist nicht konfiguriert (siehe /etc/herbstchat/server.conf)."
    sent = 0
    try:
        with smtplib.SMTP(s["host"], int(s["port"]), timeout=20) as m:
            if s.getboolean("starttls"):
                m.starttls(context=ssl.create_default_context())
            if s["user"]:
                m.login(s["user"], s["password"])
            for r in recipients:
                em = EmailMessage()
                em["From"], em["To"], em["Subject"] = s["sender"] or s["user"], r, subject
                em.set_content(text + "\n\n-- \nHerbstchat - https://herbstleyd.org")
                m.send_message(em); sent += 1
        return f"{sent} E-Mail(s) versendet."
    except Exception as e:
        return f"E-Mail-Fehler nach {sent} E-Mails: {e}"


# --------------------------------------------------------------------------- main
async def run(cfg):
    db = DB(cfg["server"]["database"])
    chat = ChatServer(cfg, db)
    app = web.Application()
    app.add_routes([web.get("/ws", chat.ws_handler),
                    web.get("/", lambda r: web.Response(text="Herbstchat Server " + VERSION))])
    sslctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    sslctx.load_cert_chain(cfg["server"]["cert"], cfg["server"]["key"])
    r1 = web.AppRunner(app); await r1.setup()
    await web.TCPSite(r1, cfg["server"]["host"], int(cfg["server"]["port"]), ssl_context=sslctx).start()
    log.info("Chat-Server läuft auf %s:%s (TLS)", cfg["server"]["host"], cfg["server"]["port"])
    if cfg["admin"]["password_hash"]:
        r2 = web.AppRunner(AdminSite(cfg, db, chat).app()); await r2.setup()
        await web.TCPSite(r2, cfg["admin"]["host"], int(cfg["admin"]["port"])).start()
        log.info("Admin-Web läuft auf http://%s:%s (nur LAN)", cfg["admin"]["host"], cfg["admin"]["port"])
    else:
        log.warning("Kein Admin-Passwort gesetzt - Admin-Web deaktiviert. 'herbstchat-server --set-admin-password'")
    asyncio.create_task(chat.cleanup_loop())
    await asyncio.Event().wait()


def set_admin_password(path, pw=None):
    pw = pw or getpass.getpass("Neues Admin-Passwort: ")
    if len(pw) < 8:
        sys.exit("Mindestens 8 Zeichen.")
    lines, done, sect = open(path).read().splitlines(), False, None
    for i, l in enumerate(lines):
        if l.strip().startswith("["):
            sect = l.strip()
        elif sect == "[admin]" and l.split("=")[0].strip() == "password_hash":
            lines[i] = "password_hash = " + hash_admin_pw(pw); done = True
    if not done:
        sys.exit("Eintrag password_hash in [admin] nicht gefunden.")
    open(path, "w").write("\n".join(lines) + "\n")
    print("Admin-Passwort gesetzt. Bitte 'systemctl restart herbstchat-server' ausführen.")


def main():
    ap = argparse.ArgumentParser(description="Herbstchat Server")
    ap.add_argument("-c", "--config", default=DEFAULT_CONF)
    ap.add_argument("--set-admin-password", action="store_true")
    ap.add_argument("--password", help=argparse.SUPPRESS)
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.set_admin_password:
        return set_admin_password(a.config, a.password)
    try:
        asyncio.run(run(load_config(a.config)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
