package io.github.sopo9880.internet_browser

import android.app.PictureInPictureParams
import android.content.Intent
import android.os.Build
import android.util.Rational
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    companion object {
        private const val CHANNEL = "internet_browser/platform"
        var callback: MethodChannel? = null
    }

    private var playbackActive = false
    private var chromiumRuntime: EmbeddedChromiumRuntime? = null

    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        val channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
        callback = channel
        chromiumRuntime = EmbeddedChromiumRuntime(this).also { it.register(engine) }
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "getNativeLibraryDir" -> result.success(applicationInfo.nativeLibraryDir)
                "enterPip" -> {
                    if (Build.VERSION.SDK_INT >= 26) {
                        try {
                            val params = PictureInPictureParams.Builder()
                                .setAspectRatio(Rational(16, 9))
                                .build()
                            result.success(enterPictureInPictureMode(params))
                        } catch (error: Exception) {
                            result.error("PIP", error.message, null)
                        }
                    } else result.error("PIP", "Android 8.0+ required", null)
                }
                "setPlayback" -> {
                    playbackActive = call.argument<Boolean>("playing") ?: false
                    val title = call.argument<String>("title") ?: "오프라인 동영상"
                    val service = Intent(this, BrowserPlaybackService::class.java)
                        .setAction(BrowserPlaybackService.ACTION_UPDATE)
                        .putExtra("title", title)
                        .putExtra("playing", playbackActive)
                    try {
                        if (Build.VERSION.SDK_INT >= 26) startForegroundService(service)
                        else startService(service)
                        if (Build.VERSION.SDK_INT >= 31) {
                            setPictureInPictureParams(
                                PictureInPictureParams.Builder()
                                    .setAspectRatio(Rational(16, 9))
                                    .setAutoEnterEnabled(playbackActive)
                                    .build()
                            )
                        }
                        result.success(true)
                    } catch (error: Exception) {
                        result.error("PLAYBACK", error.message, null)
                    }
                }
                "stopPlayback" -> {
                    playbackActive = false
                    stopService(Intent(this, BrowserPlaybackService::class.java))
                    result.success(true)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (playbackActive && Build.VERSION.SDK_INT in 26..30 &&
            !isInPictureInPictureMode) {
            try {
                enterPictureInPictureMode(
                    PictureInPictureParams.Builder()
                        .setAspectRatio(Rational(16, 9))
                        .build()
                )
            } catch (_: Exception) { }
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode)
        callback?.invokeMethod("pipChanged", isInPictureInPictureMode)
    }

    override fun onDestroy() {
        chromiumRuntime?.dispose()
        chromiumRuntime = null
        callback = null
        super.onDestroy()
    }
}
