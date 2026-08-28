package com.saarthi.phone.service

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

/**
 * Notifications padhne ka service — /notifications endpoint ke liye.
 *
 * SECURITY:
 * - Notification content mein sensitive data ho sakta hai (OTP SMS etc.)
 * - Sirf app name, title, text bhejte hain
 * - Ye data KABHI log nahi hota
 */
class SaarthiNotificationListener : NotificationListenerService() {

    companion object {
        @Volatile
        var instance: SaarthiNotificationListener? = null
            private set
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
    }

    override fun onListenerDisconnected() {
        instance = null
        super.onListenerDisconnected()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {}
    override fun onNotificationRemoved(sbn: StatusBarNotification?) {}

    /**
     * Active notifications JSON mein — Python side ke contract se match.
     */
    fun getActiveNotificationsJson(): JSONArray {
        val result = JSONArray()
        try {
            val notifs = activeNotifications ?: return result
            for (sbn in notifs) {
                val extras = sbn.notification.extras ?: continue
                val title = extras.getCharSequence("android.title")?.toString() ?: ""
                val text = extras.getCharSequence("android.text")?.toString() ?: ""
                if (title.isEmpty() && text.isEmpty()) continue
                result.put(JSONObject().apply {
                    put("app", getAppLabel(sbn.packageName))
                    put("title", title)
                    put("text", text)
                })
            }
        } catch (_: Exception) {}
        return result
    }

    private fun getAppLabel(pkg: String): String {
        return try {
            val pm = applicationContext.packageManager
            pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
        } catch (_: Exception) { pkg.substringAfterLast(".") }
    }
}
