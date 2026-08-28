package com.saarthi.phone.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.saarthi.phone.server.SaarthiHttpServer
import com.saarthi.phone.ui.MainActivity
import java.net.Inet4Address
import java.net.NetworkInterface
import java.security.SecureRandom

/**
 * Foreground Service — HTTP server alive rakhta hai background mein.
 *
 * Android ka rule: network server chalaana hai to Foreground Service + notification ZARURI.
 *
 * SECURITY:
 * - Server DEFAULT OFF — user toggle karega
 * - Sirf private network (10.x, 172.16-31.x, 192.168.x) — public/mobile data pe NAHI
 * - Token SecureRandom se (32 char) — SharedPreferences mein persist
 * - Token LOG NAHI hota (Logcat mein nahi jaata)
 */
class ServerService : Service() {

    companion object {
        private const val CHANNEL_ID = "saarthi_server"
        private const val NOTIFICATION_ID = 1001
        private const val PORT = 8080
        private const val PREFS_NAME = "saarthi_prefs"
        private const val KEY_TOKEN = "auth_token"

        @Volatile var isRunning: Boolean = false; private set
        @Volatile var serverUrl: String = ""; private set
        @Volatile var authToken: String = ""; private set

        fun start(context: Context) {
            val intent = Intent(context, ServerService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                context.startForegroundService(intent)
            else context.startService(intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, ServerService::class.java))
        }

        /** 32-char token — SecureRandom (cryptographically secure). */
        fun generateToken(): String {
            val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
            val rng = SecureRandom()
            return (1..32).map { chars[rng.nextInt(chars.length)] }.joinToString("")
        }

        /** Naya token force-generate — purana discard. */
        fun regenerateToken(context: Context) {
            authToken = generateToken()
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit().putString(KEY_TOKEN, authToken).apply()
        }
    }

    private var httpServer: SaarthiHttpServer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("Starting..."))

        // Private network check — public/mobile pe server band
        val ip = getPrivateIp()
        if (ip == null) {
            updateNotification("ERROR: Private WiFi nahi mila")
            stopSelf()
            return START_NOT_STICKY
        }

        // Token load/generate — persist in SharedPreferences
        if (authToken.isEmpty()) {
            val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val saved = prefs.getString(KEY_TOKEN, null)
            if (!saved.isNullOrEmpty()) {
                authToken = saved
            } else {
                authToken = generateToken()
                prefs.edit().putString(KEY_TOKEN, authToken).apply()
            }
        }

        // Start HTTP server
        try {
            httpServer = SaarthiHttpServer(this, authToken, PORT).also { it.start() }
            serverUrl = "http://$ip:$PORT"
            isRunning = true
            updateNotification("ON — $serverUrl")
        } catch (e: Exception) {
            updateNotification("ERROR: ${e.message}")
            isRunning = false
            stopSelf()
        }

        return START_NOT_STICKY
    }

    override fun onDestroy() {
        httpServer?.stop()
        httpServer = null
        isRunning = false
        serverUrl = ""
        super.onDestroy()
    }

    // ==================================================================
    //  NETWORK — sirf private IP
    // ==================================================================

    private fun getPrivateIp(): String? {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val ni = interfaces.nextElement()
                if (ni.isLoopback || !ni.isUp) continue
                val addrs = ni.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (addr is Inet4Address && !addr.isLoopbackAddress) {
                        val ip = addr.hostAddress ?: continue
                        if (isPrivateIp(ip)) return ip
                    }
                }
            }
            // WifiManager fallback
            val wm = applicationContext.getSystemService(WIFI_SERVICE) as? WifiManager
            val wifiIp = wm?.connectionInfo?.ipAddress ?: 0
            if (wifiIp != 0) {
                val ip = "${wifiIp and 0xff}.${(wifiIp shr 8) and 0xff}.${(wifiIp shr 16) and 0xff}.${(wifiIp shr 24) and 0xff}"
                if (isPrivateIp(ip)) return ip
            }
        } catch (_: Exception) {}
        return null
    }

    private fun isPrivateIp(ip: String): Boolean {
        val p = ip.split(".").mapNotNull { it.toIntOrNull() }
        if (p.size != 4) return false
        return when {
            p[0] == 10 -> true
            p[0] == 172 && p[1] in 16..31 -> true
            p[0] == 192 && p[1] == 168 -> true
            else -> false
        }
    }

    // ==================================================================
    //  NOTIFICATION
    // ==================================================================

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "SAARTHI Server", NotificationManager.IMPORTANCE_LOW)
            ch.description = "HTTP server running"
            getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
    }

    private fun buildNotification(status: String): Notification {
        val pi = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java).apply { flags = Intent.FLAG_ACTIVITY_SINGLE_TOP },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("SAARTHI Server")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_menu_share)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(status: String) {
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildNotification(status))
    }
}
