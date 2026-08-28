package com.saarthi.phone.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.saarthi.phone.record.ActionRecorder
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * SAARTHI ka asli "haath" — phone pe tap, swipe, type, screenshot, aur screen padhna.
 *
 * SECURITY:
 * - Password/OTP field ka text KABHI nahi bhejte (isPassword check)
 * - Token/screen data Logcat mein nahi jaata
 * - /shell jaisa kuch nahi hai, KABHI nahi banega
 */
class SaarthiAccessibilityService : AccessibilityService() {

    companion object {
        const val MAX_UI_ELEMENTS = 200

        @Volatile
        var instance: SaarthiAccessibilityService? = null
            private set
    }

    val recorder = ActionRecorder()

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    // ==================================================================
    //  USER EVENTS — recording ke liye (Phase 4 ka ASLI INAAM)
    // ==================================================================

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || !recorder.isRecording) return
        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_CLICKED -> recordClick(event)
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> recordText(event)
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> recordWindowChange(event)
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> recordScroll(event)
        }
    }

    override fun onInterrupt() {}

    // ==================================================================
    //  COMMANDS — HTTP server se aate hain
    // ==================================================================

    /** Tap at (x, y) using GestureDescription. Synchronous wait 5s. */
    fun performTap(x: Int, y: Int): Boolean {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 100))
            .build()
        return dispatchAndWait(gesture)
    }

    /** Swipe from (x1,y1) to (x2,y2). */
    fun performSwipe(x1: Int, y1: Int, x2: Int, y2: Int, durationMs: Long): Boolean {
        val path = Path().apply {
            moveTo(x1.toFloat(), y1.toFloat())
            lineTo(x2.toFloat(), y2.toFloat())
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs))
            .build()
        return dispatchAndWait(gesture)
    }

    /**
     * Type text — focused node pe ACTION_SET_TEXT.
     * Focus na ho to clipboard + ACTION_PASTE fallback.
     * SECURITY: password field mein type BLOCKED.
     */
    fun performType(text: String): Boolean {
        val focused = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)

        if (focused != null) {
            // Password field mein agent type nahi karega
            if (focused.isPassword) {
                focused.recycle()
                return false
            }
            val args = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
            }
            val result = focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
            focused.recycle()
            return result
        }

        // Fallback: clipboard se paste karo
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return false
        clipboard.setPrimaryClip(ClipData.newPlainText("saarthi", text))

        // Focused node dhundho root se
        val root = rootInActiveWindow ?: return false
        val editNode = findEditableNode(root)
        root.recycle()

        if (editNode != null) {
            if (editNode.isPassword) {
                editNode.recycle()
                return false
            }
            val result = editNode.performAction(AccessibilityNodeInfo.ACTION_PASTE)
            editNode.recycle()
            return result
        }
        return false
    }

    /**
     * Key press — back, home, recents, enter etc.
     * Hinglish naam bhi support: peeche, wapas
     */
    fun performKey(key: String): Boolean {
        return when (key.lowercase().trim()) {
            "back", "peeche", "wapas" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home", "ghar" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "recent", "recents" -> performGlobalAction(GLOBAL_ACTION_RECENTS)
            "enter" -> {
                // Enter key — focused node pe ACTION_IME_ENTER fallback
                val focused = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
                if (focused != null) {
                    val args = Bundle()
                    val result = focused.performAction(
                        AccessibilityNodeInfo.ACTION_IME_ENTER, args
                    )
                    focused.recycle()
                    result
                } else false
            }
            "notifications" -> performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS)
            "power_dialog" -> performGlobalAction(GLOBAL_ACTION_POWER_DIALOG)
            "quick_settings" -> performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS)
            else -> false
        }
    }

    /** Currently active app ka package name. MANDATORY field for /health. */
    fun getCurrentApp(): String {
        return rootInActiveWindow?.packageName?.toString() ?: ""
    }

    /**
     * UI Tree — screen ka structure padho.
     * SECURITY: isPassword nodes ka text KHALI. 200 element cap.
     */
    fun getUiTree(): JSONArray {
        val root = rootInActiveWindow ?: return JSONArray()
        val elements = JSONArray()
        traverseNode(root, elements)
        root.recycle()
        return elements
    }

    /**
     * Screenshot — API 30+ pe takeScreenshot(). Purane pe null (imaandaari).
     */
    fun performScreenshot(callback: (String?) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            callback(null)
            return
        }
        takeScreenshot(
            android.view.Display.DEFAULT_DISPLAY,
            mainExecutor,
            object : TakeScreenshotCallback {
                override fun onSuccess(screenshot: ScreenshotResult) {
                    try {
                        val bitmap = Bitmap.wrapHardwareBuffer(
                            screenshot.hardwareBuffer, screenshot.colorSpace
                        )
                        if (bitmap == null) { callback(null); return }
                        val stream = ByteArrayOutputStream()
                        bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
                        val b64 = Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP)
                        screenshot.hardwareBuffer.close()
                        bitmap.recycle()
                        callback(b64)
                    } catch (_: Exception) { callback(null) }
                }
                override fun onFailure(errorCode: Int) { callback(null) }
            }
        )
    }

    // ==================================================================
    //  PRIVATE HELPERS
    // ==================================================================

    private fun dispatchAndWait(gesture: GestureDescription): Boolean {
        val latch = CountDownLatch(1)
        var success = false
        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(g: GestureDescription?) { success = true; latch.countDown() }
            override fun onCancelled(g: GestureDescription?) { success = false; latch.countDown() }
        }, null)
        latch.await(5, TimeUnit.SECONDS)
        return success
    }

    private fun traverseNode(node: AccessibilityNodeInfo?, elements: JSONArray) {
        if (node == null || elements.length() >= MAX_UI_ELEMENTS) return
        if (!node.isVisibleToUser) return

        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        if (bounds.width() <= 0 || bounds.height() <= 0) return

        val text = node.text?.toString() ?: ""
        val desc = node.contentDescription?.toString() ?: ""
        val resId = node.viewIdResourceName ?: ""
        val clickable = node.isClickable
        val editable = node.isEditable

        // Kuch content hai to hi add karo
        if (text.isNotEmpty() || desc.isNotEmpty() || resId.isNotEmpty() || clickable || editable) {
            elements.put(JSONObject().apply {
                // SECURITY: password field ka text MASK karo
                put("text", if (node.isPassword) "" else text)
                put("content_desc", if (node.isPassword) "" else desc)
                put("resource_id", resId)
                put("class_name", node.className?.toString() ?: "")
                put("clickable", clickable)
                put("editable", editable)
                put("enabled", node.isEnabled)
                put("bounds", JSONArray().apply {
                    put(bounds.left); put(bounds.top); put(bounds.right); put(bounds.bottom)
                })
            })
        }

        for (i in 0 until node.childCount) {
            if (elements.length() >= MAX_UI_ELEMENTS) break
            val child = node.getChild(i)
            if (child != null) {
                traverseNode(child, elements)
                child.recycle()
            }
        }
    }

    private fun findEditableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isEditable && node.isFocused) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            if (child.isEditable) return child
            val found = findEditableNode(child)
            if (found != null) return found
            child.recycle()
        }
        return null
    }

    // ==================================================================
    //  RECORDING HELPERS
    // ==================================================================

    private fun recordClick(event: AccessibilityEvent) {
        val source = event.source ?: return
        val bounds = Rect()
        source.getBoundsInScreen(bounds)
        val cx = (bounds.left + bounds.right) / 2
        val cy = (bounds.top + bounds.bottom) / 2
        val text = if (source.isPassword) "{PASSWORD_FIELD}"
            else (source.text?.toString() ?: source.contentDescription?.toString() ?: "")

        if (text.isNotEmpty()) {
            recorder.record("text_pe_tap", text, intArrayOf(cx, cy))
        } else {
            recorder.record("coordinate_pe_tap", "", intArrayOf(cx, cy))
        }
        source.recycle()
    }

    private fun recordText(event: AccessibilityEvent) {
        val source = event.source ?: return
        val text = if (source.isPassword) "{PASSWORD}"
            else (event.text?.joinToString("") ?: "")
        recorder.record("text_likho", text, null)
        source.recycle()
    }

    private fun recordWindowChange(event: AccessibilityEvent) {
        val pkg = event.packageName?.toString() ?: return
        if (pkg == recorder.lastPackage) return
        recorder.lastPackage = pkg
        recorder.record("app_kholo", pkg, null)
    }

    private fun recordScroll(@Suppress("UNUSED_PARAMETER") event: AccessibilityEvent) {
        recorder.record("scroll_karo", "", null)
    }
}
