# SAARTHI Phone — ProGuard Rules
-keep class fi.iki.elonen.** { *; }
-keep class com.saarthi.phone.service.** { *; }
-keep class com.saarthi.phone.server.** { *; }
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-dontwarn androidx.compose.**
