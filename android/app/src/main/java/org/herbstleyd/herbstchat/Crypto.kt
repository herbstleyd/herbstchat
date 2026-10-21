package org.herbstleyd.herbstchat

import android.util.Base64
import com.goterl.lazysodium.SodiumAndroid
import com.sun.jna.NativeLong
import java.math.BigInteger
import java.security.MessageDigest

/**
 * Kompatibel zum Desktop-Client (PyNaCl):
 *  - Argon2id (opslimit MODERATE = 3, memlimit INTERACTIVE = 64 MiB) -> 64 Byte, [0:32] Auth, [32:64] Tresor
 *  - SecretBox / Box: Ausgabe = Nonce (24 Byte) || Chiffretext (wie PyNaCl encrypt())
 */
object Crypto {
    private val na by lazy { SodiumAndroid() }

    private const val NONCE = 24
    private const val MAC = 16
    private const val OPS_MODERATE = 3L
    private const val MEM_INTERACTIVE = 67108864L
    private const val ALG_ARGON2ID13 = 2
    const val SALT_BYTES = 16

    fun b64e(b: ByteArray): String = Base64.encodeToString(b, Base64.NO_WRAP)
    fun b64d(s: String): ByteArray = Base64.decode(s, Base64.DEFAULT)

    fun random(n: Int): ByteArray = ByteArray(n).also { na.randombytes_buf(it, n) }

    fun selfTest(): Boolean = try {
        val k = random(32); val c = secretEncrypt(k, "ok".toByteArray())
        String(secretDecrypt(k, c)) == "ok"
    } catch (e: Throwable) { false }

    /** Liefert (auth, vault) */
    fun derive(password: String, salt: ByteArray): Pair<ByteArray, ByteArray> {
        val out = ByteArray(64)
        val pw = password.toByteArray(Charsets.UTF_8)
        val r = na.crypto_pwhash(out, 64, pw, pw.size.toLong(), salt, OPS_MODERATE, NativeLong(MEM_INTERACTIVE), ALG_ARGON2ID13)
        if (r != 0) throw IllegalStateException("Argon2id fehlgeschlagen (zu wenig Speicher?)")
        return out.copyOfRange(0, 32) to out.copyOfRange(32, 64)
    }

    fun secretEncrypt(key: ByteArray, msg: ByteArray): ByteArray {
        val nonce = random(NONCE)
        val ct = ByteArray(msg.size + MAC)
        na.crypto_secretbox_easy(ct, msg, msg.size.toLong(), nonce, key)
        return nonce + ct
    }

    fun secretDecrypt(key: ByteArray, data: ByteArray): ByteArray {
        require(data.size >= NONCE + MAC)
        val nonce = data.copyOfRange(0, NONCE); val ct = data.copyOfRange(NONCE, data.size)
        val out = ByteArray(ct.size - MAC)
        if (na.crypto_secretbox_open_easy(out, ct, ct.size.toLong(), nonce, key) != 0)
            throw SecurityException("Entschlüsselung fehlgeschlagen")
        return out
    }

    /** (publicKey, secretKey) */
    fun keypair(): Pair<ByteArray, ByteArray> {
        val pk = ByteArray(32); val sk = ByteArray(32)
        na.crypto_box_keypair(pk, sk)
        return pk to sk
    }

    fun publicFromSecret(sk: ByteArray): ByteArray = ByteArray(32).also { na.crypto_scalarmult_base(it, sk) }

    fun boxEncrypt(sk: ByteArray, peerPk: ByteArray, msg: ByteArray): ByteArray {
        val nonce = random(NONCE)
        val ct = ByteArray(msg.size + MAC)
        na.crypto_box_easy(ct, msg, msg.size.toLong(), nonce, peerPk, sk)
        return nonce + ct
    }

    fun boxDecrypt(sk: ByteArray, peerPk: ByteArray, data: ByteArray): ByteArray {
        require(data.size >= NONCE + MAC)
        val nonce = data.copyOfRange(0, NONCE); val ct = data.copyOfRange(NONCE, data.size)
        val out = ByteArray(ct.size - MAC)
        if (na.crypto_box_open_easy(out, ct, ct.size.toLong(), nonce, peerPk, sk) != 0)
            throw SecurityException("Entschlüsselung fehlgeschlagen")
        return out
    }

    fun sha256(b: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(b)
    fun hex(b: ByteArray): String = b.joinToString("") { "%02x".format(it) }

    /** identisch zu safety_number() im Desktop-Client */
    fun safetyNumber(a: String, b: String): String {
        val ka = b64d(a); val kb = b64d(b)
        val sorted = listOf(ka, kb).sortedWith { x, y -> compareUnsigned(x, y) }
        val h = hex(sha256(sorted[0] + sorted[1]))
        val digits = BigInteger(h.substring(0, 40), 16).toString().take(30).padStart(30, '0')
        return digits.chunked(5).joinToString(" ")
    }

    fun keyFingerprint(pubB64: String): String =
        hex(sha256(b64d(pubB64))).take(32).chunked(4).joinToString(" ")

    private fun compareUnsigned(x: ByteArray, y: ByteArray): Int {
        for (i in 0 until minOf(x.size, y.size)) {
            val c = (x[i].toInt() and 0xff) - (y[i].toInt() and 0xff)
            if (c != 0) return c
        }
        return x.size - y.size
    }
}
