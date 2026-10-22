@file:OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)

package org.herbstleyd.herbstchat

import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

val EMOJIS = "😀 😂 😊 😍 😘 😎 🤔 😅 😢 😭 😡 👍 👎 👋 🙏 👏 💪 ❤️ 💔 🔥 🎉 🍂 🍁 ☕ 🍺 🎂 🌞 🌧️ ⭐ ✅ ❌ ❓".split(" ")
val ACCENTS = linkedMapOf("Herbst-Orange" to "#c8641e", "Ahorn-Rot" to "#b83b3b", "Waldgrün" to "#3d8b4f",
    "Himmelblau" to "#2f7fc1", "Violett" to "#7d4fb3", "ICQ-Grün" to "#5fae3b")

fun hexColor(s: String) = Color(android.graphics.Color.parseColor(s))

// ====================================================================== Theme
@Composable
fun HerbstTheme(content: @Composable () -> Unit) {
    ChatCore.themeRev
    val s = ChatCore.settings
    val dark = when (s.theme) { "dunkel" -> true; "hell" -> false; else -> isSystemInDarkTheme() }
    val a = hexColor(s.accent)
    val scheme = if (dark) darkColorScheme(primary = a, onPrimary = Color.White, secondary = a,
        background = Color(0xFF1F2124), surface = Color(0xFF1F2124), surfaceVariant = Color(0xFF33363B),
        surfaceContainer = Color(0xFF2A2D31), onBackground = Color(0xFFE8E8E8), onSurface = Color(0xFFE8E8E8),
        primaryContainer = a.copy(alpha = .35f), onPrimaryContainer = Color.White)
    else lightColorScheme(primary = a, onPrimary = Color.White, secondary = a,
        background = Color(0xFFF6F3EF), surface = Color(0xFFF6F3EF), surfaceVariant = Color(0xFFEFE9E1),
        surfaceContainer = Color(0xFFFFFFFF), onBackground = Color(0xFF262626), onSurface = Color(0xFF262626),
        primaryContainer = a.copy(alpha = .18f), onPrimaryContainer = Color(0xFF262626))
    val d = LocalDensity.current
    CompositionLocalProvider(LocalDensity provides Density(d.density, d.fontScale * s.fontScale)) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

// ====================================================================== Root
@Composable
fun HerbstchatApp() = HerbstTheme {
    val c = ChatCore
    c.rev
    var screen by remember { mutableStateOf("main") }
    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        when (c.phase) {
            Phase.LOGIN -> if (screen == "settings") SettingsScreen { screen = "main" } else LoginScreen { screen = "settings" }
            Phase.CONNECTING -> ConnectingScreen()
            Phase.READY -> when {
                screen == "settings" -> SettingsScreen { screen = "main" }
                c.current != null -> ChatScreen(c.current!!)
                else -> ContactsScreen(openSettings = { screen = "settings" })
            }
        }
    }
    GlobalDialogs()
}

@Composable
fun GlobalDialogs() {
    val c = ChatCore
    c.pinProblem?.let { p ->
        val nice = Connection.nice(p.fingerprint)
        if (p.changed) AlertDialog(onDismissRequest = {}, icon = { Icon(Icons.Default.Warning, null, tint = Color(0xFFE74C3C)) },
            title = { Text("Zertifikat hat sich geändert!") },
            text = { SelectionContainer { Text("WARNUNG: Das Server-Zertifikat von ${p.key} hat sich geändert.\n\nNeuer Fingerabdruck:\n$nice\n\n" +
                    "Wenn der Server nicht neu installiert wurde, könnte jemand die Verbindung abhören. Die Verbindung wurde abgebrochen.\n\n" +
                    "Zum Zurücksetzen in den Einstellungen „Server-Vertrauen zurücksetzen“ wählen.") } },
            confirmButton = { TextButton({ c.rejectPin() }) { Text("OK") } })
        else AlertDialog(onDismissRequest = {}, icon = { Icon(Icons.Default.Lock, null) },
            title = { Text("Erste Verbindung") },
            text = { SelectionContainer { Text("Erste Verbindung zu ${p.key}.\n\nZertifikat-Fingerabdruck (SHA-256):\n$nice\n\n" +
                    "Vergleiche ihn mit /etc/herbstchat/zertifikat-fingerabdruck.txt auf dem Server.\n\nDiesem Server vertrauen?") } },
            confirmButton = { Button({ c.acceptPin(p) }) { Text("Vertrauen") } },
            dismissButton = { TextButton({ c.rejectPin() }) { Text("Abbrechen") } })
    }
    c.alert?.let { a ->
        AlertDialog(onDismissRequest = { c.alert = null }, title = { Text(a.title) },
            text = { SelectionContainer { Text(a.text) } }, confirmButton = { TextButton({ c.alert = null }) { Text("OK") } })
    }
    c.searchResults?.let { res ->
        AlertDialog(onDismissRequest = { c.searchResults = null }, title = { Text("Kontakt hinzufügen") },
            text = {
                if (res.isEmpty()) Text("Kein Benutzer gefunden.")
                else Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text("Gefundene Benutzer:", style = MaterialTheme.typography.labelMedium)
                    res.forEach { (id, nick) ->
                        ListItem(headlineContent = { Text(nick) }, leadingContent = { Icon(Icons.Default.PersonAdd, null) },
                            modifier = Modifier.clickable { c.addContact(id); c.searchResults = null })
                    }
                }
            }, confirmButton = { TextButton({ c.searchResults = null }) { Text("Schließen") } })
    }
}

// ====================================================================== Login
@Composable
fun LoginScreen(openSettings: () -> Unit) {
    val c = ChatCore; val s = c.settings
    var tab by remember { mutableIntStateOf(0) }
    var nick by remember { mutableStateOf(if (s.rememberNick) s.lastNick else "") }
    var pw by remember { mutableStateOf("") }
    var remember by remember { mutableStateOf(s.stayLoggedIn) }
    var mail by remember { mutableStateOf("") }
    var rnick by remember { mutableStateOf("") }
    var rpw by remember { mutableStateOf("") }
    var rpw2 by remember { mutableStateOf("") }
    var server by remember { mutableStateOf(s.server) }
    var port by remember { mutableStateOf(s.port.toString()) }
    var showServer by remember { mutableStateOf(false) }
    var localErr by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(c.registeredNick) { c.registeredNick?.let { nick = it; tab = 0; c.registeredNick = null } }

    fun applyServer(): Boolean {
        val p = port.toIntOrNull()
        if (server.isBlank() || p == null || p !in 1..65535) { localErr = "Bitte gültigen Server und Port angeben."; return false }
        s.server = server.trim(); s.port = p; return true
    }

    fun login() {
        localErr = null
        if (nick.isBlank() || pw.isEmpty()) { localErr = "Bitte Nickname und Passwort eingeben."; return }
        if (!applyServer()) return
        s.stayLoggedIn = remember
        c.startLogin(nick.trim(), pw, remember)
    }

    fun register() {
        localErr = null
        val m = mail.trim()
        when {
            "@" !in m || "." !in m.substringAfterLast("@") -> localErr = "Bitte eine gültige E-Mail-Adresse angeben."
            rnick.trim().length < 3 -> localErr = "Der Nickname muss mindestens 3 Zeichen lang sein."
            rpw.length < 6 -> localErr = "Das Passwort muss mindestens 6 Zeichen lang sein."
            rpw != rpw2 -> localErr = "Die Passwörter stimmen nicht überein."
            applyServer() -> c.startRegister(m, rnick.trim(), rpw)
        }
    }

    Column(Modifier.fillMaxSize().systemBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            IconButton(openSettings) { Icon(Icons.Default.Settings, "Einstellungen") }
        }
        AppLogo(72)
        Spacer(Modifier.height(12.dp))
        Text("Herbstchat", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        Text("Sicher chatten – Ende-zu-Ende verschlüsselt", color = Color.Gray, textAlign = TextAlign.Center)
        Spacer(Modifier.height(20.dp))
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainer)) {
            Column(Modifier.padding(16.dp)) {
                TabRow(tab, containerColor = Color.Transparent) {
                    Tab(tab == 0, { tab = 0; localErr = null }, text = { Text("Anmelden") })
                    Tab(tab == 1, { tab = 1; localErr = null }, text = { Text("Registrieren") })
                }
                Spacer(Modifier.height(12.dp))
                val enabled = !c.loginBusy
                if (tab == 0) {
                    OutlinedTextField(nick, { nick = it }, label = { Text("Nickname") }, singleLine = true, enabled = enabled,
                        modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next))
                    PasswordField(pw, { pw = it }, "Passwort", enabled, ImeAction.Done) { login() }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(remember, { remember = it }, enabled = enabled); Text("Angemeldet bleiben")
                    }
                    Button(::login, Modifier.fillMaxWidth(), enabled = enabled) { Text("Anmelden") }
                } else {
                    OutlinedTextField(mail, { mail = it }, label = { Text("E-Mail (für Wartungshinweise)") }, singleLine = true,
                        enabled = enabled, modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next))
                    OutlinedTextField(rnick, { rnick = it }, label = { Text("Nickname (3–24 Zeichen)") }, singleLine = true,
                        enabled = enabled, modifier = Modifier.fillMaxWidth(), keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next))
                    PasswordField(rpw, { rpw = it }, "Passwort (mind. 6 Zeichen)", enabled, ImeAction.Next) {}
                    PasswordField(rpw2, { rpw2 = it }, "Passwort wiederholen", enabled, ImeAction.Done) { register() }
                    Text("Wichtig: Dein Passwort schützt deinen privaten Schlüssel. Es kann nicht wiederhergestellt werden – " +
                        "auch nicht vom Serverbetreiber.", style = MaterialTheme.typography.bodySmall, color = Color.Gray,
                        modifier = Modifier.padding(vertical = 8.dp))
                    Button(::register, Modifier.fillMaxWidth(), enabled = enabled) { Text("Account erstellen") }
                }
                if (c.loginBusy) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 12.dp))
                val msg = localErr ?: c.loginStatus
                if (msg.isNotEmpty()) Text(msg, color = if (localErr != null || c.loginError) Color(0xFFE74C3C) else Color.Gray,
                    modifier = Modifier.padding(top = 8.dp), style = MaterialTheme.typography.bodyMedium)
            }
        }
        Spacer(Modifier.height(12.dp))
        TextButton({ showServer = !showServer }) {
            Icon(Icons.Default.Dns, null); Spacer(Modifier.width(6.dp)); Text("Server: ${s.server}:${s.port}")
        }
        if (showServer) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(server, { server = it }, label = { Text("Server") }, singleLine = true, modifier = Modifier.weight(1f))
            OutlinedTextField(port, { port = it.filter(Char::isDigit).take(5) }, label = { Text("Port") }, singleLine = true,
                modifier = Modifier.width(100.dp), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        }
    }
}

@Composable
fun PasswordField(v: String, on: (String) -> Unit, label: String, enabled: Boolean, ime: ImeAction, done: () -> Unit) {
    OutlinedTextField(v, on, label = { Text(label) }, singleLine = true, enabled = enabled,
        visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ime),
        keyboardActions = KeyboardActions(onDone = { done() }))
}

@Composable
fun AppLogo(size: Int) {
    Box(Modifier.size(size.dp).clip(RoundedCornerShape((size / 4).dp)).background(MaterialTheme.colorScheme.primary),
        contentAlignment = Alignment.Center) {
        Text("H", color = Color.White, fontWeight = FontWeight.Bold, fontSize = (size * 0.55).sp)
    }
}

@Composable
fun ConnectingScreen() {
    val c = ChatCore
    Column(Modifier.fillMaxSize().systemBarsPadding().padding(32.dp), verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        AppLogo(72); Spacer(Modifier.height(24.dp))
        CircularProgressIndicator(); Spacer(Modifier.height(16.dp))
        Text(c.connLabel, textAlign = TextAlign.Center)
        Spacer(Modifier.height(24.dp))
        OutlinedButton({ c.cancelResume() }) { Text("Abmelden") }
    }
}

// ====================================================================== Kontakte
@Composable
fun StatusDot(status: String, size: Int = 12) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(Color(STATUS_COLOR[status] ?: 0xFF7F8C8D)))
}

@Composable
fun ContactsScreen(openSettings: () -> Unit) {
    val c = ChatCore; c.rev
    var filter by remember { mutableStateOf("") }
    var addOpen by remember { mutableStateOf(false) }
    var statusMenu by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf(false) }
    val uri = LocalUriHandler.current

    Scaffold(topBar = {
        TopAppBar(title = {
            Column {
                Text(c.me?.nick ?: "Herbstchat", fontWeight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { statusMenu = true }) {
                    StatusDot(if (c.connected) c.myStatus else "offline", 9); Spacer(Modifier.width(5.dp))
                    Text(if (c.connected) STATUS_LABEL[c.myStatus]!! else c.connLabel, style = MaterialTheme.typography.bodySmall,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Icon(Icons.Default.ArrowDropDown, null, Modifier.size(18.dp))
                }
                DropdownMenu(statusMenu, { statusMenu = false }) {
                    MY_STATUSES.forEach { st ->
                        DropdownMenuItem(text = { Text(STATUS_LABEL[st]!!) }, leadingIcon = { StatusDot(st) },
                            onClick = { c.setStatus(st); statusMenu = false })
                    }
                }
            }
        }, actions = {
            IconButton({ addOpen = true }) { Icon(Icons.Default.PersonAdd, "Kontakt hinzufügen") }
            IconButton({ menu = true }) { Icon(Icons.Default.MoreVert, "Menü") }
            DropdownMenu(menu, { menu = false }) {
                DropdownMenuItem(text = { Text("Einstellungen") }, leadingIcon = { Icon(Icons.Default.Settings, null) },
                    onClick = { menu = false; openSettings() })
                DropdownMenuItem(text = { Text("Mein Schlüssel-Fingerabdruck") }, leadingIcon = { Icon(Icons.Default.Fingerprint, null) },
                    onClick = { menu = false; c.alert = Alert("Herbstchat", "Dein Schlüssel-Fingerabdruck:\n\n" + Crypto.keyFingerprint(c.me!!.pubkey)) })
                DropdownMenuItem(text = { Text("Info über Herbstchat") }, leadingIcon = { Icon(Icons.Default.Info, null) },
                    onClick = { menu = false; info = true })
                DropdownMenuItem(text = { Text("Webseite herbstleyd.org") }, leadingIcon = { Icon(Icons.Default.Public, null) },
                    onClick = { menu = false; uri.openUri(WEBSITE) })
                HorizontalDivider()
                DropdownMenuItem(text = { Text("Abmelden") }, leadingIcon = { Icon(Icons.AutoMirrored.Filled.Logout, null) },
                    onClick = { menu = false; c.logout() })
            }
        }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surfaceContainer))
    }, floatingActionButton = {
        FloatingActionButton({ addOpen = true }, containerColor = MaterialTheme.colorScheme.primary) { Icon(Icons.Default.Add, "Kontakt hinzufügen") }
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            OutlinedTextField(filter, { filter = it }, placeholder = { Text("Kontakte durchsuchen ...") }, singleLine = true,
                leadingIcon = { Icon(Icons.Default.Search, null) }, modifier = Modifier.fillMaxWidth().padding(12.dp, 8.dp),
                shape = RoundedCornerShape(24.dp))
            val rows = c.contactRows(filter)
            if (rows.isEmpty()) Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center) {
                Text("Willkommen bei Herbstchat 🍂", style = MaterialTheme.typography.titleLarge)
                Spacer(Modifier.height(8.dp))
                Text("Füge über das + einen Kontakt hinzu.", color = Color.Gray, textAlign = TextAlign.Center)
            }
            LazyColumn(Modifier.fillMaxSize()) {
                items(rows, key = { it.id }) { r -> ContactRow(r) }
            }
        }
    }
    if (addOpen) {
        var q by remember { mutableStateOf("") }
        AlertDialog(onDismissRequest = { addOpen = false }, title = { Text("Kontakt hinzufügen") },
            text = { OutlinedTextField(q, { q = it }, label = { Text("Nickname suchen (Anfang genügt)") }, singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { if (q.isNotBlank()) { c.search(q.trim()); addOpen = false } })) },
            confirmButton = { Button({ if (q.isNotBlank()) { c.search(q.trim()); addOpen = false } }) { Text("Suchen") } },
            dismissButton = { TextButton({ addOpen = false }) { Text("Abbrechen") } })
    }
    if (info) InfoDialog { info = false }
}

private val timeFmt = SimpleDateFormat("HH:mm", Locale.GERMANY)
private val dayFmt = SimpleDateFormat("dd.MM.yyyy", Locale.GERMANY)

@Composable
fun ContactRow(r: ChatCore.Row) {
    ListItem(
        modifier = Modifier.clickable { ChatCore.openChat(r.id) },
        leadingContent = {
            Box {
                Box(Modifier.size(44.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
                    contentAlignment = Alignment.Center) {
                    Text(r.nick.take(1).uppercase(), fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 18.sp)
                }
                Box(Modifier.align(Alignment.BottomEnd).size(14.dp).clip(CircleShape).background(MaterialTheme.colorScheme.background),
                    contentAlignment = Alignment.Center) { StatusDot(r.status, 10) }
            }
        },
        headlineContent = {
            Text(r.nick + if (r.inContacts) "" else "  (nicht in Kontakten)", fontWeight = if (r.unread > 0) FontWeight.Bold else FontWeight.Normal,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
        },
        supportingContent = {
            val t = if (ChatCore.isTyping(r.id)) "schreibt ..." else r.last?.let { (if (it.me) "Du: " else "") + it.text.replace('\n', ' ') }
                ?: STATUS_LABEL[r.status]!!
            Text(t, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color.Gray)
        },
        trailingContent = {
            Column(horizontalAlignment = Alignment.End) {
                r.last?.let {
                    val d = Date((it.ts * 1000).toLong())
                    Text(if (dayFmt.format(d) == dayFmt.format(Date())) timeFmt.format(d) else dayFmt.format(d).substring(0, 6),
                        style = MaterialTheme.typography.labelSmall, color = Color.Gray)
                }
                if (r.unread > 0) Badge(containerColor = Color(0xFFE74C3C)) { Text(minOf(r.unread, 99).toString()) }
            }
        },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent)
    )
}

@Composable
fun InfoDialog(close: () -> Unit) {
    val uri = LocalUriHandler.current
    AlertDialog(onDismissRequest = close, icon = { AppLogo(56) }, title = { Text("Herbstchat $VERSION") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), horizontalAlignment = Alignment.CenterHorizontally) {
                listOf("Schön, dass du da bist! 🍂",
                    "Herbstchat ist ein kleiner, privater Messenger – gemacht für Freunde, Familie und Bekannte. Ohne Werbung, ohne Datensammelei und ohne Tracking.",
                    "Alle Nachrichten werden auf deinem Gerät verschlüsselt und erst beim Empfänger wieder entschlüsselt. Nicht einmal der Serverbetreiber kann sie lesen.",
                    "Viel Spaß beim Chatten – und denk dran: ein nettes Wort kostet nichts.").forEach {
                    Text(it, textAlign = TextAlign.Center, modifier = Modifier.padding(bottom = 10.dp))
                }
                TextButton({ uri.openUri(WEBSITE) }) { Text("herbstleyd.org", fontWeight = FontWeight.Bold, fontSize = 18.sp) }
                Text("Herzliche Grüße, Herbstleyd", color = Color.Gray)
            }
        }, confirmButton = { TextButton(close) { Text("Schließen") } })
}

// ====================================================================== Chat
@Composable
fun ChatScreen(id: Int) {
    val c = ChatCore; c.rev
    var input by remember(id) { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    var emoji by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf<String?>(null) }
    var tick by remember { mutableIntStateOf(0) }
    LaunchedEffect(id) { while (true) { delay(1000); tick++ } }
    BackHandler { c.current = null }
    val history = c.history(id)
    val listState = rememberLazyListState()
    LaunchedEffect(id, history.size) { if (history.isNotEmpty()) listState.scrollToItem(history.size - 1) }
    val status = c.statusOf(id)
    val accent = MaterialTheme.colorScheme.primary
    val inContacts = c.contacts.containsKey(id)

    fun doSend() {
        val t = input.trim()
        if (t.isNotEmpty() && c.sendMessage(t)) input = ""
    }

    Scaffold(topBar = {
        TopAppBar(navigationIcon = { IconButton({ c.current = null }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Zurück") } },
            title = {
                Column {
                    Text(c.nickOf(id), fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        tick
                        StatusDot(status, 8); Spacer(Modifier.width(5.dp))
                        Text(if (c.isTyping(id)) "schreibt ..." else STATUS_LABEL[status]!!, style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.width(8.dp))
                        Icon(Icons.Default.Lock, null, Modifier.size(12.dp), tint = Color.Gray)
                        Text(" E2E", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
                    }
                }
            }, actions = {
                IconButton({ menu = true }) { Icon(Icons.Default.MoreVert, "Menü") }
                DropdownMenu(menu, { menu = false }) {
                    if (!inContacts) DropdownMenuItem(text = { Text("Zu Kontakten hinzufügen") }, leadingIcon = { Icon(Icons.Default.PersonAdd, null) },
                        onClick = { menu = false; c.addContact(id) })
                    DropdownMenuItem(text = { Text("Sicherheitsnummer prüfen") }, leadingIcon = { Icon(Icons.Default.VerifiedUser, null) },
                        onClick = {
                            menu = false
                            c.safetyNumber(id)?.let {
                                c.alert = Alert("Sicherheitsnummer", "Sicherheitsnummer mit ${c.nickOf(id)}:\n\n$it\n\n" +
                                    "Vergleicht diese Nummer z. B. persönlich oder telefonisch. Stimmt sie bei beiden überein, " +
                                    "kann niemand – auch nicht der Server – eure Nachrichten mitlesen.")
                            }
                        })
                    DropdownMenuItem(text = { Text("Verlauf löschen") }, leadingIcon = { Icon(Icons.Default.DeleteSweep, null) },
                        onClick = { menu = false; confirm = "clear" })
                    if (inContacts) DropdownMenuItem(text = { Text("Kontakt entfernen") }, leadingIcon = { Icon(Icons.Default.PersonRemove, null) },
                        onClick = { menu = false; confirm = "remove" })
                }
            }, colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surfaceContainer))
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().imePadding()) {
            if (!c.connected) Text(c.connLabel, Modifier.fillMaxWidth().background(Color(0xFFF1C40F).copy(alpha = .3f)).padding(6.dp),
                textAlign = TextAlign.Center, style = MaterialTheme.typography.bodySmall)
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = listState, contentPadding = PaddingValues(10.dp)) {
                if (history.isEmpty()) item {
                    Text("Noch keine Nachrichten. Sag hallo! 👋\nNachrichten an Offline-Kontakte werden zugestellt, sobald sie sich anmelden.",
                        Modifier.fillMaxWidth().padding(top = 40.dp), textAlign = TextAlign.Center, color = Color.Gray)
                }
                items(history.size) { i ->
                    val m = history[i]
                    val day = dayFmt.format(Date((m.ts * 1000).toLong()))
                    val prevDay = if (i > 0) dayFmt.format(Date((history[i - 1].ts * 1000).toLong())) else null
                    if (day != prevDay) Text("— $day —", Modifier.fillMaxWidth().padding(vertical = 6.dp), textAlign = TextAlign.Center,
                        color = Color.Gray, style = MaterialTheme.typography.labelSmall)
                    Bubble(m, accent)
                }
            }
            Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceContainer).navigationBarsPadding().padding(6.dp),
                verticalAlignment = Alignment.Bottom) {
                Box {
                    IconButton({ emoji = true }) { Icon(Icons.Default.EmojiEmotions, "Emoji") }
                    DropdownMenu(emoji, { emoji = false }) {
                        FlowRow(Modifier.width(300.dp).padding(6.dp)) {
                            EMOJIS.forEach { e ->
                                Text(e, fontSize = 24.sp, modifier = Modifier.clickable { input += e; emoji = false }.padding(6.dp))
                            }
                        }
                    }
                }
                OutlinedTextField(input, { v ->
                    if (c.settings.enterSends && v.endsWith("\n") && v.length == input.length + 1) { doSend(); return@OutlinedTextField }
                    input = v; c.onTyping()
                }, Modifier.weight(1f).heightIn(max = 160.dp), placeholder = { Text("Nachricht schreiben ...") },
                    shape = RoundedCornerShape(22.dp), maxLines = 6)
                IconButton(::doSend, enabled = input.isNotBlank()) {
                    Icon(Icons.AutoMirrored.Filled.Send, "Senden", tint = if (input.isNotBlank()) accent else Color.Gray)
                }
            }
        }
    }
    when (confirm) {
        "clear" -> ConfirmDialog("Verlauf mit diesem Kontakt löschen? (auch auf dem Server und allen deinen Geräten)", { confirm = null }) { c.clearChat(id) }
        "remove" -> ConfirmDialog("${c.nickOf(id)} aus der Kontaktliste entfernen?", { confirm = null }) { c.removeContact(id) }
    }
}

@Composable
fun ConfirmDialog(text: String, close: () -> Unit, ok: () -> Unit) {
    AlertDialog(onDismissRequest = close, text = { Text(text) },
        confirmButton = { Button({ ok(); close() }) { Text("Ja") } }, dismissButton = { TextButton(close) { Text("Abbrechen") } })
}

private val URL_RE = Regex("https?://[^\\s<]+")

fun linkify(text: String, color: Color): AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in URL_RE.findAll(text)) {
        append(text.substring(last, m.range.first))
        withLink(LinkAnnotation.Url(m.value, TextLinkStyles(SpanStyle(color = color, textDecoration = TextDecoration.Underline)))) { append(m.value) }
        last = m.range.last + 1
    }
    append(text.substring(last))
}

@Composable
fun Bubble(m: Msg, accent: Color) {
    val s = ChatCore.settings
    val pad = if (s.compact) 6.dp else 10.dp
    if (m.sys) {
        Text(m.text, Modifier.fillMaxWidth().padding(6.dp), textAlign = TextAlign.Center, color = Color(0xFFE67E22))
        return
    }
    val time = if (s.showTime) timeFmt.format(Date((m.ts * 1000).toLong())) else ""
    Row(Modifier.fillMaxWidth().padding(vertical = if (s.compact) 1.dp else 3.dp),
        horizontalArrangement = if (m.me) Arrangement.End else Arrangement.Start) {
        val bg = if (m.me) accent else MaterialTheme.colorScheme.surfaceVariant
        val fg = if (m.me) Color.White else MaterialTheme.colorScheme.onSurface
        Column(Modifier.widthIn(max = 300.dp).clip(RoundedCornerShape(14.dp, 14.dp, if (m.me) 4.dp else 14.dp, if (m.me) 14.dp else 4.dp))
            .background(bg).padding(pad)) {
            SelectionContainer { Text(linkify(m.text, fg), color = fg) }
            val tick = if (m.me) when (m.state) {
                "sending" -> " ⏳"; "queued" -> " ✉ zugestellt sobald online"; "failed" -> " ⚠ fehlgeschlagen"; else -> " ✓"
            } else ""
            if (time.isNotEmpty() || tick.isNotEmpty())
                Text(time + tick, style = MaterialTheme.typography.labelSmall,
                    color = if (m.me) Color(0xFFFFE9D6) else Color.Gray, modifier = Modifier.align(Alignment.End))
        }
    }
}

// ====================================================================== Einstellungen
@Composable
fun SettingsScreen(back: () -> Unit) {
    val c = ChatCore; val s = c.settings
    val ctx = LocalContext.current
    var r by remember { mutableIntStateOf(0) }
    var dialog by remember { mutableStateOf<String?>(null) }
    BackHandler(onBack = back)
    fun changed() { r++; c.themeRev++ }

    @Composable
    fun Switch(text: String, get: () -> Boolean, set: (Boolean) -> Unit) {
        r
        ListItem(headlineContent = { Text(text) }, trailingContent = { Switch(get(), { set(it); changed() }) },
            modifier = Modifier.clickable { set(!get()); changed() }, colors = ListItemDefaults.colors(containerColor = Color.Transparent))
    }

    @Composable
    fun Header(t: String) = Text(t, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(16.dp, 18.dp, 16.dp, 4.dp))

    @Composable
    fun Action(text: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit) =
        ListItem(headlineContent = { Text(text) }, leadingContent = { Icon(icon, null) }, modifier = Modifier.clickable(onClick = onClick),
            colors = ListItemDefaults.colors(containerColor = Color.Transparent))

    Scaffold(topBar = {
        TopAppBar(title = { Text("Einstellungen") }, navigationIcon = { IconButton(back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Zurück") } },
            colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surfaceContainer))
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize().verticalScroll(rememberScrollState())) {
            r
            Header("Darstellung")
            Text("Farbschema", Modifier.padding(horizontal = 16.dp))
            Row(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("system" to "System", "hell" to "Hell", "dunkel" to "Dunkel").forEach { (k, l) ->
                    FilterChip(s.theme == k, { s.theme = k; changed() }, label = { Text(l) })
                }
            }
            Text("Akzentfarbe", Modifier.padding(16.dp, 10.dp, 16.dp, 4.dp))
            FlowRow(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ACCENTS.forEach { (name, hex) ->
                    FilterChip(s.accent == hex, { s.accent = hex; changed() }, label = { Text(name) },
                        leadingIcon = { Box(Modifier.size(14.dp).clip(CircleShape).background(hexColor(hex))) })
                }
            }
            Text("Schriftgröße: ${(s.fontScale * 100).toInt()} %", Modifier.padding(16.dp, 10.dp, 16.dp, 0.dp))
            Slider(s.fontScale, { s.fontScale = (it * 20).toInt() / 20f; changed() }, valueRange = 0.8f..1.5f, steps = 13,
                modifier = Modifier.padding(horizontal = 16.dp))
            Switch("Uhrzeit bei Nachrichten anzeigen", { s.showTime }) { s.showTime = it }
            Switch("Kompakte Nachrichtenansicht", { s.compact }) { s.compact = it }
            Switch("Offline-Kontakte anzeigen", { s.showOffline }) { s.showOffline = it }

            Header("Benachrichtigungen")
            Switch("Benachrichtigung bei neuer Nachricht", { s.notify }) { s.notify = it }
            Switch("Nachrichtenvorschau zeigen", { s.notifyPreview }) { s.notifyPreview = it }
            Switch("Melden, wenn ein Kontakt online kommt", { s.notifyOnline }) { s.notifyOnline = it }
            Action("Ton & Vibration (Android-Einstellungen)", Icons.Default.NotificationsActive) {
                ctx.startActivity(Intent(AndroidSettings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(AndroidSettings.EXTRA_APP_PACKAGE, ctx.packageName))
            }
            Text("Im Status „Beschäftigt“ gibt es keine Benachrichtigungen.", Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.bodySmall, color = Color.Gray)

            Header("Chat & Privatsphäre")
            Switch("Eingabetaste sendet", { s.enterSends }) { s.enterSends = it }
            Switch("Anderen anzeigen, dass ich tippe", { s.sendTyping }) { s.sendTyping = it }
            Switch("Chatverlauf lokal (verschlüsselt) speichern", { s.saveHistory }) { s.saveHistory = it; c.saveProfile() }
            Switch("Nickname merken", { s.rememberNick }) { s.rememberNick = it; if (!it) s.lastNick = "" }
            if (c.loggedIn) Action("Gesamten lokalen Chatverlauf löschen", Icons.Default.DeleteForever) { dialog = "clearall" }

            Header("Hintergrund")
            Switch("Im Hintergrund verbunden bleiben", { s.background }) {
                s.background = it
                if (it && c.loggedIn) ChatService.start(ctx) else if (!it) ChatService.stop(ctx)
            }
            val pm = ctx.getSystemService(PowerManager::class.java)
            if (!pm.isIgnoringBatteryOptimizations(ctx.packageName))
                Action("Akku-Optimierung für Herbstchat abschalten (empfohlen)", Icons.Default.BatteryAlert) {
                    try {
                        ctx.startActivity(Intent(AndroidSettings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${ctx.packageName}")))
                    } catch (_: Exception) { ctx.startActivity(Intent(AndroidSettings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
                }
            Text("Damit Nachrichten auch bei ausgeschaltetem Bildschirm sofort ankommen.", Modifier.padding(horizontal = 16.dp),
                style = MaterialTheme.typography.bodySmall, color = Color.Gray)

            if (c.loggedIn) {
                Header("Konto")
                Action("Passwort ändern", Icons.Default.Password) { dialog = "pw" }
                Action("E-Mail-Adresse ändern", Icons.Default.Email) { dialog = "mail" }
                Action("Mein Schlüssel-Fingerabdruck", Icons.Default.Fingerprint) {
                    c.alert = Alert("Herbstchat", "Dein Schlüssel-Fingerabdruck:\n\n" + Crypto.keyFingerprint(c.me!!.pubkey))
                }
            }

            Header("Server")
            if (c.loggedIn) Text("${s.server}:${s.port} (zum Ändern abmelden)", Modifier.padding(horizontal = 16.dp))
            else Text("${s.server}:${s.port} (änderbar auf dem Anmeldebildschirm)", Modifier.padding(horizontal = 16.dp))
            Action("Server-Vertrauen zurücksetzen", Icons.Default.GppMaybe) { c.pins.clear(); c.alert = Alert("Herbstchat", "Zertifikats-Pins gelöscht.") }

            Header("Allgemein")
            Action("Einstellungen auf Standard zurücksetzen", Icons.Default.RestartAlt) { s.resetDefaults(); changed() }
            Text("Herbstchat $VERSION für Android", Modifier.padding(16.dp), color = Color.Gray, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.navigationBarsPadding())
        }
    }

    when (dialog) {
        "clearall" -> ConfirmDialog("Gesamten Chatverlauf löschen? Er wird auch auf dem Server und damit auf allen deinen Geräten gelöscht.", { dialog = null }) { c.clearAllHistory() }
        "mail" -> {
            var mail by remember { mutableStateOf(c.me?.email ?: "") }
            AlertDialog(onDismissRequest = { dialog = null }, title = { Text("E-Mail-Adresse ändern") },
                text = { OutlinedTextField(mail, { mail = it }, singleLine = true, label = { Text("Neue E-Mail-Adresse") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email)) },
                confirmButton = { Button({ if (mail.isNotBlank()) c.changeEmail(mail.trim()); dialog = null }) { Text("Speichern") } },
                dismissButton = { TextButton({ dialog = null }) { Text("Abbrechen") } })
        }
        "pw" -> {
            var old by remember { mutableStateOf("") }
            var n1 by remember { mutableStateOf("") }
            var n2 by remember { mutableStateOf("") }
            var err by remember { mutableStateOf<String?>(null) }
            var busy by remember { mutableStateOf(false) }
            AlertDialog(onDismissRequest = { if (!busy) dialog = null }, title = { Text("Passwort ändern") },
                text = {
                    Column {
                        PasswordField(old, { old = it }, "Altes Passwort", !busy, ImeAction.Next) {}
                        PasswordField(n1, { n1 = it }, "Neues Passwort (mind. 6 Zeichen)", !busy, ImeAction.Next) {}
                        PasswordField(n2, { n2 = it }, "Neues Passwort wiederholen", !busy, ImeAction.Done) {}
                        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 8.dp))
                        err?.let { Text(it, color = Color(0xFFE74C3C), modifier = Modifier.padding(top = 6.dp)) }
                    }
                },
                confirmButton = {
                    Button({
                        if (n1.length < 6 || n1 != n2) { err = "Neues Passwort zu kurz oder nicht identisch."; return@Button }
                        busy = true; err = null
                        c.changePassword(old, n1) { e -> busy = false; err = e }
                    }, enabled = !busy) { Text("Ändern") }
                },
                dismissButton = { TextButton({ dialog = null }, enabled = !busy) { Text("Abbrechen") } })
            // Erfolg kommt als Alert vom Server -> Dialog schließen
            LaunchedEffect(c.alert) { if (busy && c.alert != null) dialog = null }
        }
    }
}
