package com.saarthi.phone.server

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import com.saarthi.phone.service.SaarthiAccessibilityService
import com.saarthi.phone.service.SaarthiNotificationListener
import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * HTTP Server — laptop se phone ko command bhejne ka raasta.
 *
 * Python side ka AccessibilityDevice isi contract pe depend karta hai.
 * Har endpoint EXACTLY wahi JSON format deta hai.
 *
 * SECURITY:
 * 1. Bearer token har request pe (constant-time compare)
 * 2. Token galat/missing → 401, koi action nahi
 * 3. OTP/PIN/password /type pe BLOCKED
 * 4. /shell jaisa endpoint NAHI hai — banane ki koshish bhi mat karna
 * 5. Token/screen data LOG NAHI hota (Logcat mein nahi jaata)
 */
class SaarthiHttpServer(
    private val context: Context,
    private val token: String,
    port: Int = 8080
) : NanoHTTPD(port) {

    // OTP/PIN/password patterns — Python safety.py se SAME
    private val blockedPatterns = listOf(
        Regex("\\b(otp|o\\.t\\.p)\\b", RegexOption.IGNORE_CASE),
        Regex("\\b(cvv|cvc)\\b", RegexOption.IGNORE_CASE),
        Regex("\\b(upi\\s*pin|atm\\s*pin|card\\s*pin|mpin)\\b", RegexOption.IGNORE_CASE),
        Regex("\\bpassword\\s*(hai|is|:)\\s*\\S+", RegexOption.IGNORE_CASE),
    )

    override fun serve(session: IHTTPSession): Response {
        // STEP 1: Token auth — CONSTANT TIME compare (MessageDigest.isEqual)
        val authHeader = session.headers["authorization"] ?: ""
        val provided = if (authHeader.startsWith("Bearer ", ignoreCase = true))
            authHeader.substring(7) else ""

        if (!constantTimeEquals(provided, token)) {
            return jsonResponse(Response.Status.UNAUTHORIZED,
                JSONObject().put("ok", false).put("error", "unauthorized"))
        }

        // STEP 2: Route
        val uri = session.uri ?: "/"
        val method = session.method

        return try {
            when {
                uri == "/health" && method == Method.GET -> handleHealth()
                uri == "/tap" && method == Method.POST -> handleTap(session)
                uri == "/swipe" && method == Method.POST -> handleSwipe(session)
                uri == "/type" && method == Method.POST -> handleType(session)
                uri == "/key" && method == Method.POST -> handleKey(session)
                uri == "/ui_tree" && method == Method.GET -> handleUiTree()
                uri == "/screenshot" && method == Method.GET -> handleScreenshot()
                uri == "/launch_app" && method == Method.POST -> handleLaunchApp(session)
                uri == "/close_app" && method == Method.POST -> handleCloseApp(session)
                uri == "/apps" && method == Method.GET -> handleApps()
                uri == "/notifications" && method == Method.GET -> handleNotifications()
                uri == "/record/start" && method == Method.POST -> handleRecordStart()
                uri == "/record/stop" && method == Method.POST -> handleRecordStop()
                uri == "/recorded_actions" && method == Method.GET -> handleRecordedActions()
                else -> jsonResponse(Response.Status.NOT_FOUND,
                    JSONObject().put("ok", false).put("error", "not found: $uri"))
            }
        } catch (e: Exception) {
            jsonResponse(Response.Status.INTERNAL_ERROR,
                JSONObject().put("ok", false).put("error", "internal: ${e.message}"))
        }
    }

    // ==================================================================
    //  HANDLERS
    // ==================================================================

    private fun handleHealth(): Response {
        val service = getService()
        val dm = context.resources.displayMetrics
        val json = JSONObject().apply {
            put("ok", true)
            put("model", Build.MODEL)
            put("android", Build.VERSION.RELEASE)
            put("screen", JSONArray().put(dm.widthPixels).put(dm.heightPixels))
            // MANDATORY: banking screenshot lock isi pe depend karta hai
            put("current_app", service?.getCurrentApp() ?: "")
        }
        return jsonResponse(Response.Status.OK, json)
    }

    private fun handleTap(session: IHTTPSession): Response {
        val body = parseBody(session) ?: return badRequest("body parse nahi hua")
        val x = body.optInt("x", -1)
        val y = body.optInt("y", -1)
        if (x < 0 || y < 0) return badRequest("x aur y zaruri hain")
        val service = getService() ?: return serviceUnavailable()
        return okResponse(service.performTap(x, y))
    }

    private fun handleSwipe(session: IHTTPSession): Response {
        val body = parseBody(session) ?: return badRequest("body parse nahi hua")
        val x1 = body.optInt("x1", -1); val y1 = body.optInt("y1", -1)
        val x2 = body.optInt("x2", -1); val y2 = body.optInt("y2", -1)
        val duration = body.optLong("duration_ms", 300)
        if (x1 < 0 || y1 < 0 || x2 < 0 || y2 < 0) return badRequest("coordinates zaruri hain")
        val service = getService() ?: return serviceUnavailable()
        return okResponse(service.performSwipe(x1, y1, x2, y2, duration))
    }

    private fun handleType(session: IHTTPSession): Response {
        val body = parseBody(session) ?: return badRequest("body parse nahi hua")
        val text = body.optString("text", "")
        if (text.isEmpty()) return badRequest("text zaruri hai")

        // SECURITY: OTP/PIN/password BLOCKED
        for (pattern in blockedPatterns) {
            if (pattern.containsMatchIn(text)) {
                return jsonResponse(Response.Status.FORBIDDEN,
                    JSONObject().put("ok", false)
                        .put("error", "OTP/PIN/password type karna BLOCKED — security rule"))
            }
        }
        // 6-digit potential OTP
        if (text.trim().matches(Regex("^\\d{6}$"))) {
            return jsonResponse(Response.Status.FORBIDDEN,
                JSONObject().put("ok", false)
                    .put("error", "6-digit number OTP lag raha hai — user khud daalega"))
        }

        val service = getService() ?: return serviceUnavailable()
        return okResponse(service.performType(text))
    }

    private fun handleKey(session: IHTTPSession): Response {
        val body = parseBody(session) ?: return badRequest("body parse nahi hua")
        val key = body.optString("key", "")
        if (key.isEmpty()) return badRequest("key zaruri hai")
        val service = getService() ?: return serviceUnavailable()
        return okResponse(service.performKey(key))
    }

    private fun handleUiTree(): Response {
        val service = getService() ?: return serviceUnavailable()
        return jsonResponse(Response.Status.OK,
            JSONObject().put("elements", service.getUiTree()))
    }

    private fun handleScreenshot(): Response {
        val service = getService() ?: return serviceUnavailable()
        val latch = CountDownLatch(1)
        var b64: String? = null
        service.performScreenshot { result -> b64 = result; latch.countDown() }
        latch.await(15, TimeUnit.SECONDS)
        if (b64 == null) {
            return badRequest("Screenshot nahi mila. API 30+ chahiye ya permission issue.")
        }
        return jsonResponse(Response.Status.OK,
            JSONObject().put("ok", true).put("image_b64", b64))
    }

    private fun handleLaunchApp(session: IHTTPSession): Response {
        val body = parseBody(session) ?: return badRequest("body parse nahi hua")
        val app = body.optString("app", "")
        if (app.isEmpty()) return badRequest("app zaruri hai")

        // Pehle exact package try karo
        var intent = context.packageManager.getLaunchIntentForPackage(app)

        // Na mile to naam se dhoondho (fuzzy match)
        if (intent == null) {
            val pkg = findPackageByName(app)
            if (pkg != null) intent = context.packageManager.getLaunchIntentForPackage(pkg)
        }

        if (intent == null) return badRequest("'$app' nahi khul paya — installed hai?")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return okResponse(true)
    }

    private fun handleCloseApp(session: IHTTPSession): Response {
        // Accessibility se force-stop nahi hota — limitation imaandaari se batao
        val service = getService() ?: return serviceUnavailable()
        service.performKey("home")
        return okResponse(true)
    }

    private fun handleApps(): Response {
        val pm = context.packageManager
        val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
            .map { it.packageName }
            .sorted()
        return jsonResponse(Response.Status.OK, JSONObject().put("apps", JSONArray(apps)))
    }

    private fun handleNotifications(): Response {
        val listener = SaarthiNotificationListener.instance
        val notifs = listener?.getActiveNotificationsJson() ?: JSONArray()
        return jsonResponse(Response.Status.OK, JSONObject().put("notifications", notifs))
    }

    private fun handleRecordStart(): Response {
        val service = getService() ?: return serviceUnavailable()
        service.recorder.start()
        return okResponse(true)
    }

    private fun handleRecordStop(): Response {
        val service = getService() ?: return serviceUnavailable()
        service.recorder.stop()
        // NOTE: recorded actions CLEAR NAHI karte — Python pull karega
        return okResponse(true)
    }

    private fun handleRecordedActions(): Response {
        val service = getService() ?: return serviceUnavailable()
        return jsonResponse(Response.Status.OK,
            JSONObject().put("actions", service.recorder.getActions()))
    }

    // ==================================================================
    //  HELPERS
    // ==================================================================

    private fun getService(): SaarthiAccessibilityService? = SaarthiAccessibilityService.instance

    private fun serviceUnavailable(): Response = jsonResponse(
        Response.Status.lookup(503),
        JSONObject().put("ok", false)
            .put("error", "AccessibilityService chalu nahi hai. Settings mein SAARTHI ON karo."))

    private fun badRequest(msg: String): Response = jsonResponse(
        Response.Status.BAD_REQUEST,
        JSONObject().put("ok", false).put("error", msg))

    private fun okResponse(success: Boolean): Response = jsonResponse(
        if (success) Response.Status.OK else Response.Status.INTERNAL_ERROR,
        JSONObject().put("ok", success))

    private fun jsonResponse(status: Response.IStatus, json: JSONObject): Response =
        newFixedLengthResponse(status, "application/json", json.toString())

    private fun parseBody(session: IHTTPSession): JSONObject? {
        return try {
            val files = HashMap<String, String>()
            session.parseBody(files)
            JSONObject(files["postData"] ?: return null)
        } catch (_: Exception) { null }
    }

    /**
     * CONSTANT-TIME token compare — timing attack se bachao.
     * MessageDigest.isEqual ALWAYS pura compare karta hai.
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.isEmpty() || b.isEmpty()) return false
        return MessageDigest.isEqual(a.toByteArray(Charsets.UTF_8), b.toByteArray(Charsets.UTF_8))
    }

    /** Package name fuzzy search — "paytm" se "net.one97.paytm" milna chahiye */
    private fun findPackageByName(query: String): String? {
        val lower = query.lowercase()
        val pm = context.packageManager
        return pm.getInstalledApplications(PackageManager.GET_META_DATA)
            .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
            .firstOrNull { it.packageName.lowercase().contains(lower) }
            ?.packageName
    }
}
