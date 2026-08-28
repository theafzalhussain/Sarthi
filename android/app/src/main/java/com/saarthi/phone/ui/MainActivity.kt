package com.saarthi.phone.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import com.saarthi.phone.ui.theme.SaarthiPhoneTheme

class MainActivity : ComponentActivity() {

    /**
     * POST_NOTIFICATIONS ka runtime request.
     *
     * ⚠️ YE ZARURI HAI, "achha hota to" wali cheez NAHI.
     *
     * Android 13 (API 33) se notification ke liye RUNTIME permission
     * chahiye. Hamara HTTP server ek FOREGROUND SERVICE hai, aur uska
     * notification hi user ko batata hai ki server ON hai (aur usse
     * band karne ka raasta deta hai).
     *
     * Permission na mile to service chalti rehti hai par notification
     * DIKHTA NAHI. Nateeja: user ko pata hi nahi chalta ki uske phone pe
     * server chalu hai. Security wali cheez chup-chaap background mein
     * chalna sabse bura hai — isliye permission maangte hain.
     */
    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* mile ya na mile, app chalta rehta hai — sirf notification chhup jaayega */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        askNotificationPermission()

        setContent {
            SaarthiPhoneTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    SaarthiApp()
                }
            }
        }
    }

    private fun askNotificationPermission() {
        // Android 12 aur neeche pe ye permission exist hi nahi karti
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return

        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
}
