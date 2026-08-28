package com.saarthi.phone.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.saarthi.phone.service.SaarthiAccessibilityService
import com.saarthi.phone.service.SaarthiNotificationListener
import com.saarthi.phone.service.ServerService
import kotlinx.coroutines.delay

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SaarthiApp() {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Home", "Permissions", "Recording")

    Scaffold(
        topBar = {
            CenterAlignedTopAppBar(title = { Text("SAARTHI Phone", fontWeight = FontWeight.Bold) })
        }
    ) { padding ->
        Column(modifier = Modifier.padding(padding)) {
            TabRow(selectedTabIndex = selectedTab) {
                tabs.forEachIndexed { i, title ->
                    Tab(selected = selectedTab == i, onClick = { selectedTab = i },
                        text = { Text(title) })
                }
            }
            when (selectedTab) {
                0 -> HomeScreen()
                1 -> PermissionsScreen()
                2 -> RecordingScreen()
            }
        }
    }
}

// ==================================================================
//  HOME — server ON/OFF, IP:port, token
// ==================================================================

@Composable
fun HomeScreen() {
    val context = LocalContext.current
    var isRunning by remember { mutableStateOf(ServerService.isRunning) }
    var serverUrl by remember { mutableStateOf(ServerService.serverUrl) }
    var token by remember { mutableStateOf(ServerService.authToken) }

    LaunchedEffect(Unit) {
        while (true) {
            isRunning = ServerService.isRunning
            serverUrl = ServerService.serverUrl
            token = ServerService.authToken
            delay(1000)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Status card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = if (isRunning) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(modifier = Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    if (isRunning) "SERVER ON" else "SERVER OFF",
                    fontSize = 28.sp, fontWeight = FontWeight.Bold,
                    color = if (isRunning) MaterialTheme.colorScheme.onPrimaryContainer
                    else MaterialTheme.colorScheme.onSurfaceVariant
                )
                if (isRunning && serverUrl.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Text(serverUrl, fontSize = 20.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Medium)
                }
            }
        }

        // Toggle button
        Button(
            onClick = { if (isRunning) ServerService.stop(context) else ServerService.start(context) },
            modifier = Modifier.fillMaxWidth().height(56.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isRunning) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
            )
        ) { Text(if (isRunning) "STOP SERVER" else "START SERVER", fontSize = 18.sp) }

        // Token + copy
        if (isRunning && token.isNotEmpty()) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Token (laptop pe .env mein daalo):", fontSize = 14.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Text(token, fontFamily = FontFamily.Monospace, fontSize = 13.sp)
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = {
                        val cb = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        cb.setPrimaryClip(ClipData.newPlainText("token", token))
                        Toast.makeText(context, "Token copied!", Toast.LENGTH_SHORT).show()
                    }, modifier = Modifier.fillMaxWidth()) { Text("COPY TOKEN") }
                }
            }

            // .env hint
            Card(modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Laptop pe .env mein:", fontWeight = FontWeight.Medium, fontSize = 14.sp)
                    Spacer(Modifier.height(4.dp))
                    Text("SAARTHI_PHONE_URL=$serverUrl\nSAARTHI_PHONE_TOKEN=$token",
                        fontFamily = FontFamily.Monospace, fontSize = 12.sp)
                }
            }
        }

        // Warning
        if (!isRunning) {
            Text("Server sirf private WiFi pe chalega.\nPublic WiFi / mobile data pe NAHI.",
                fontSize = 13.sp, textAlign = TextAlign.Center,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ==================================================================
//  PERMISSIONS
// ==================================================================

@Composable
fun PermissionsScreen() {
    val context = LocalContext.current
    var a11yEnabled by remember { mutableStateOf(false) }
    var notifEnabled by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        while (true) {
            a11yEnabled = SaarthiAccessibilityService.instance != null
            notifEnabled = SaarthiNotificationListener.instance != null
            delay(1000)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Permissions", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text("Dono permissions ZARURI hain:", fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)

        // Accessibility
        PermissionCard(
            title = "Accessibility Service",
            enabled = a11yEnabled,
            onClick = { context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) },
            desc = if (a11yEnabled) "ON — connected" else "OFF — tap/swipe/screenshot nahi chalega"
        )

        // Notification
        PermissionCard(
            title = "Notification Access",
            enabled = notifEnabled,
            onClick = { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) },
            desc = if (notifEnabled) "ON — connected" else "OFF — /notifications nahi chalega"
        )

        Spacer(Modifier.height(8.dp))
        Card(modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Kyun chahiye?", fontWeight = FontWeight.Medium)
                Spacer(Modifier.height(8.dp))
                Text("Accessibility: screen padhna, tap/swipe karna, recording.\n\n" +
                    "Notification Access: /notifications endpoint ke liye.", fontSize = 13.sp)
            }
        }

        Text("Google Play pe publish NAHI ho sakta (policy). Sirf personal use / sideload.",
            fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
    }
}

@Composable
fun PermissionCard(title: String, enabled: Boolean, onClick: () -> Unit, desc: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.padding(16.dp).fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Medium)
                Text(desc, fontSize = 13.sp,
                    color = if (enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)
            }
            Button(onClick = onClick, enabled = !enabled) {
                Text(if (enabled) "Done" else "Open")
            }
        }
    }
}

// ==================================================================
//  RECORDING — "Dikha Do" mode
// ==================================================================

@Composable
fun RecordingScreen() {
    val context = LocalContext.current
    var isRecording by remember { mutableStateOf(false) }
    var actionCount by remember { mutableIntStateOf(0) }
    var actions by remember { mutableStateOf(listOf<String>()) }

    LaunchedEffect(Unit) {
        while (true) {
            val svc = SaarthiAccessibilityService.instance
            if (svc != null) {
                isRecording = svc.recorder.isRecording
                actionCount = svc.recorder.count()
                // Last 20 actions
                val arr = svc.recorder.getActions()
                val list = mutableListOf<String>()
                val start = maxOf(0, arr.length() - 20)
                for (i in start until arr.length()) {
                    val obj = arr.optJSONObject(i) ?: continue
                    val act = obj.optString("action", "?")
                    val txt = obj.optString("target_text", "")
                    list.add("${i + 1}. $act${if (txt.isNotEmpty()) " \"$txt\"" else ""}")
                }
                actions = list
            }
            delay(500)
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Dikha Do Mode", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text("Recording ON karo, phone pe kaam karo, phir laptop pe 'phone se seekh le' bolo.",
            fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)

        // Status card
        Card(modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = if (isRecording) MaterialTheme.colorScheme.errorContainer
                else MaterialTheme.colorScheme.surfaceVariant)) {
            Column(modifier = Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(if (isRecording) "RECORDING..." else "Ready",
                    fontSize = 20.sp, fontWeight = FontWeight.Bold,
                    color = if (isRecording) MaterialTheme.colorScheme.onErrorContainer
                    else MaterialTheme.colorScheme.onSurfaceVariant)
                if (isRecording) Text("$actionCount actions recorded")
            }
        }

        // Buttons
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = {
                    val svc = SaarthiAccessibilityService.instance
                    if (svc != null) { if (isRecording) svc.recorder.stop() else svc.recorder.start() }
                    else Toast.makeText(context, "Accessibility ON nahi hai — Permissions tab dekho", Toast.LENGTH_LONG).show()
                },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isRecording) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
            ) { Text(if (isRecording) "STOP" else "START Recording") }

            if (!isRecording && actionCount > 0) {
                OutlinedButton(onClick = { SaarthiAccessibilityService.instance?.recorder?.clear() }) {
                    Text("Clear")
                }
            }
        }

        // Action list
        if (actions.isNotEmpty()) {
            Text("Recorded Actions:", fontWeight = FontWeight.Medium, fontSize = 14.sp)
            Card(modifier = Modifier.fillMaxWidth().weight(1f)) {
                LazyColumn(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(actions) { Text(it, fontSize = 13.sp, fontFamily = FontFamily.Monospace) }
                }
            }
        }

        // Instructions
        if (!isRecording && actionCount == 0) {
            Card(modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Kaise use karo:", fontWeight = FontWeight.Medium)
                    Spacer(Modifier.height(4.dp))
                    Text("1. START dabao\n2. Phone pe kaam karo (dhire-dhire)\n" +
                        "3. STOP dabao\n4. Laptop pe bolo: 'phone se seekh le'\n" +
                        "5. Skill ban jaayegi — agli baar naam bolna kaafi", fontSize = 13.sp)
                }
            }
        }
    }
}
