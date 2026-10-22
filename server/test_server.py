#!/usr/bin/env python3
"""Protokoll-Selbsttest für den Herbstchat-Server (Login, Zustellung, Verlaufs-Sync, Admin-Web).
Startet einen temporären Server und spielt zwei Geräte von "alice" und eines von "bob" durch.
Benötigt: python3-aiohttp, python3-nacl, openssl.   Aufruf: python3 test_server.py"""
import asyncio, aiohttp, json, base64, nacl.public, nacl.utils, sys, os, subprocess, tempfile, time
b64e=lambda b: base64.b64encode(b).decode(); b64d=base64.b64decode
HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="hc-test-")
PORT, APORT = 47999, 8099
URL=f"wss://127.0.0.1:{PORT}/ws"
ADMIN = {"Authorization": "Basic " + b64e(b"admin:testtest123")}
class Dev:
    def __init__(s, nick, auth, priv): s.nick, s.auth, s.priv = nick, auth, priv
    async def connect(s, sess):
        s.ws = await sess.ws_connect(URL, ssl=False)
        await s.ws.send_json({"t":"login","nick":s.nick,"auth":b64e(s.auth)})
        s.login = await s.recv("login_ok"); s.id = s.login["id"]; return s
    async def recv(s, t, timeout=3):
        while True:
            m = await asyncio.wait_for(s.ws.receive_json(), timeout)
            if m["t"] == t: return m
            if m["t"] == "error": raise RuntimeError(m)
    async def sync(s, since=0):
        out=[]
        while True:
            await s.ws.send_json({"t":"history_delta","since":since}); d = await s.recv("history_delta")
            out += d["delta"]; since = d["last"]
            if not d["more"]: return out, d
async def reg(sess, nick):
    ws = await sess.ws_connect(URL, ssl=False); priv=nacl.public.PrivateKey.generate(); auth=nacl.utils.random(32)
    await ws.send_json({"t":"register","email":f"{nick}@x.de","nick":nick,"salt":b64e(nacl.utils.random(16)),"auth":b64e(auth),"pubkey":b64e(bytes(priv.public_key)),"enc_priv":"AAAA"})
    assert (await ws.receive_json())["t"]=="register_ok"; await ws.close(); return auth, priv
async def main():
    async with aiohttp.ClientSession() as sess:
        aauth, apriv = await reg(sess, "alice"); bauth, bpriv = await reg(sess, "bob")
        a1 = await Dev("alice", aauth, apriv).connect(sess); a2 = await Dev("alice", aauth, apriv).connect(sess)
        b = await Dev("bob", bauth, bpriv).connect(sess)
        print("login ok, history_counter:", a1.login["history_counter"])
        box_ab = nacl.public.Box(apriv, bpriv.public_key); box_ba = nacl.public.Box(bpriv, apriv.public_key)
        for i in range(3):
            await a1.ws.send_json({"t":"msg","to":b.id,"payload":b64e(box_ab.encrypt(json.dumps({"text":f"hallo {i}","ts":0}).encode())),"cid":f"c{i}"})
            sent = await a1.recv("sent"); m = await b.recv("msg"); cp = await a2.recv("msg_copy")
            assert json.loads(box_ba.decrypt(b64d(m["payload"])))["text"] == f"hallo {i}"
            assert json.loads(box_ab.decrypt(b64d(cp["payload"])))["text"] == f"hallo {i}" and cp["cid"] == f"c{i}"
        await b.ws.send_json({"t":"msg","to":a1.id,"payload":b64e(box_ba.encrypt(json.dumps({"text":"antwort","ts":0}).encode())),"cid":"x"})
        await b.recv("sent"); await a1.recv("msg"); await a2.recv("msg")
        print("live delivery + msg_copy ok")
        # neues Gerät a3 synchronisiert alles
        a3 = await Dev("alice", aauth, apriv).connect(sess)
        rows, last = await a3.sync(0)
        txt = [(r["out"], json.loads(box_ab.decrypt(b64d(r["blob"])))["text"]) for r in rows]
        print("a3 sync:", txt, "users:", list(last["users"])); assert len(rows)==4 and txt[-1]==(False,"antwort") and all(o for o,_ in txt[:3])
        assert a3.login["history_counter"] == rows[-1]["id"]
        rows2,_ = await a3.sync(rows[-1]["id"]); assert rows2 == []
        brow,_ = await b.sync(0); assert len(brow)==4 and [r["out"] for r in brow]==[False,False,False,True]
        print("per-user counter + Richtung ok")
        # Upload alt (hv=2) + ohne hv ignoriert
        await a1.ws.send_json({"t":"history_upload","entries":[{"contact_id":b.id,"blob":"x","ts":1}]}); assert (await a1.recv("history_uploaded"))["n"]==0
        ent=[{"contact_id":b.id,"out":True,"blob":b64e(box_ab.encrypt(json.dumps({"text":f"alt {i}","ts":1000+i}).encode())),"ts":1000.0+i} for i in range(200)]
        await a1.ws.send_json({"t":"history_upload","hv":2,"entries":ent}); assert (await a1.recv("history_uploaded"))["n"]==200
        print("upload ok")
        # Paging: große Einträge
        big=[{"contact_id":b.id,"out":False,"blob":"A"*60000,"ts":2000.0} for _ in range(30)]
        for i in range(0,30,2):
            await a1.ws.send_json({"t":"history_upload","hv":2,"entries":big[i:i+2]}); await a1.recv("history_uploaded")
        pages=0; since=0
        while True:
            await a3.ws.send_json({"t":"history_delta","since":since}); m = await a3.ws.receive()
            assert len(m.data) < 700_000, len(m.data); d=json.loads(m.data); pages+=1; since=d["last"]
            if not d["more"]: break
        print("paging ok, pages:", pages)
        await a1.ws.send_json({"t":"history_clear","contact_id":b.id}); await a1.recv("history_cleared")
        r,_ = await a3.sync(0); assert r==[]; print("clear ok")
        await a1.ws.send_json({"t":"history_updated","counter":5}); print("compat:", await a1.recv("history_updated_ok"))
        async with sess.get(f"http://127.0.0.1:{APORT}/", headers=ADMIN) as r:
            assert r.status == 200
        for p in ("/users", "/user/1", "/broadcast", "/settings", "/log", "/debug", "/export.csv"):
            async with sess.get(f"http://127.0.0.1:{APORT}{p}", headers=ADMIN) as r:
                assert r.status == 200, (p, r.status)
        print("admin-web ok")


def run():
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                    "-days", "2", "-keyout", f"{TMP}/key.pem", "-out", f"{TMP}/cert.pem", "-subj", "/CN=localhost"],
                   check=True, capture_output=True)
    conf = f"{TMP}/server.conf"
    open(conf, "w").write(f"""[server]\nhost = 127.0.0.1\nport = {PORT}\ncert = {TMP}/cert.pem\nkey = {TMP}/key.pem
database = {TMP}/db/herbstchat.db\n[admin]\nhost = 127.0.0.1\nport = {APORT}\nuser = admin\npassword_hash =\n""")
    srv = os.path.join(HERE, "herbstchat_server.py")
    subprocess.run([sys.executable, srv, "-c", conf, "--set-admin-password", "--password", "testtest123"], check=True,
                   capture_output=True)
    p = subprocess.Popen([sys.executable, srv, "-c", conf], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(2)
        asyncio.run(main())
    finally:
        p.terminate(); out = p.communicate()[0]
    if "Traceback" in out:
        print(out); sys.exit("Server-Fehler im Log")
    print("ALLE SERVER-TESTS OK")


if __name__ == "__main__":
    run()
