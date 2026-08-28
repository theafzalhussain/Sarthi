package com.saarthi.phone.record

import org.json.JSONArray
import org.json.JSONObject

/**
 * User ke manual taps record karta hai — Phase 4 ka ASLI INAAM.
 *
 * SECURITY:
 * - Password/OTP field ka text KABHI record nahi hota
 * - Placeholder {PASSWORD} daalta hai taaki replay pe user khud bhare
 *
 * DEDUP: Same action+text 300ms ke andar aaye to skip (Android ek tap pe
 * multiple events bhejta hai).
 */
class ActionRecorder {

    @Volatile
    var isRecording: Boolean = false
        private set

    @Volatile
    var lastPackage: String = ""

    private val actions = mutableListOf<JSONObject>()

    // Dedup — last event ka timestamp aur fingerprint
    private var lastEventTime: Long = 0
    private var lastEventFingerprint: String = ""

    // Python ka RECORDABLE_ACTIONS — sirf ye 8 accept hote hain
    private val allowedActions = setOf(
        "app_kholo", "app_band_karo", "text_pe_tap", "coordinate_pe_tap",
        "text_likho", "key_dabao", "scroll_karo", "command_chalao"
    )

    fun start() {
        synchronized(actions) { actions.clear() }
        lastPackage = ""
        lastEventTime = 0
        lastEventFingerprint = ""
        isRecording = true
    }

    /** Stop recording — actions CLEAR NAHI karo, Python pull karega phir. */
    fun stop() {
        isRecording = false
    }

    /**
     * Ek action record karo. 300ms dedup built-in.
     */
    fun record(action: String, targetText: String, coords: IntArray?) {
        if (!isRecording) return
        if (action !in allowedActions) return

        // 300ms dedup — same fingerprint 300ms ke andar skip
        val now = System.currentTimeMillis()
        val fingerprint = "$action|$targetText"
        if (fingerprint == lastEventFingerprint && (now - lastEventTime) < 300) return
        lastEventTime = now
        lastEventFingerprint = fingerprint

        val entry = JSONObject().apply {
            put("action", action)
            put("params", JSONObject().apply {
                when (action) {
                    "text_pe_tap" -> put("text", targetText)
                    "text_likho" -> put("text", targetText)
                    "app_kholo" -> put("app", targetText)
                    "scroll_karo" -> put("direction", "down")
                }
            })
            put("target_text", targetText)
            if (coords != null && coords.size >= 2) {
                put("target_coords", JSONArray().apply { put(coords[0]); put(coords[1]) })
            } else {
                put("target_coords", JSONObject.NULL)
            }
            put("notes", "")
        }

        synchronized(actions) { actions.add(entry) }
    }

    fun getActions(): JSONArray {
        synchronized(actions) {
            val arr = JSONArray()
            actions.forEach { arr.put(it) }
            return arr
        }
    }

    fun count(): Int = synchronized(actions) { actions.size }

    fun clear() {
        synchronized(actions) { actions.clear() }
        lastPackage = ""
    }
}
