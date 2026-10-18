package io.github.sopo9880.internet_browser

import android.app.Activity
import android.content.Context
import android.view.View
import android.widget.TextView
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.StandardMessageCodec
import io.flutter.plugin.platform.PlatformView
import io.flutter.plugin.platform.PlatformViewFactory

/**
 * The Android Chromium embedder boundary. Implementations MUST use Chromium
 * content + Chrome's extension host, not android.webkit.WebView or intents.
 *
 * The real Chromium engine is supplied as an app-linked native module. This
 * contract is intentionally compiled without such a module so incomplete
 * builds cannot pretend the required AdBlock extension is supported.
 */
interface EmbeddedChromiumEngine {
    fun createPage(
        context: Context,
        tabId: Int,
        initialUrl: String,
        event: (Map<String, Any?>) -> Unit
    ): View

    fun invoke(tabId: Int, command: String, args: Map<String, Any?>): Any?
    fun extensions(command: String, args: Map<String, Any?>): Any?
    fun capabilities(): Map<String, Any?>
    fun closePage(tabId: Int)
}

/**
 * The provider class must be bundled INSIDE the APK/AAB and implement
 * EmbeddedChromiumEngine. We never delegate to a different browser app.
 * Missing/invalid provider => unavailable; NO silent Android WebView fallback.
 */
class EmbeddedChromiumRuntime(private val activity: Activity) {
    companion object {
        private const val PROVIDER_CLASS =
            "io.github.sopo9880.internet_browser.chromium.ChromiumEngineProvider"
        private const val NAVIGATION_CHANNEL = "internet_browser/chromium_navigation"
        private const val EXTENSION_CHANNEL = "internet_browser/chromium_extensions"
        private const val EVENT_CHANNEL = "internet_browser/chromium_events"
        private const val VIEW_ID = "internet_browser/chromium_view"
    }

    private val embedded: EmbeddedChromiumEngine? = loadProvider()
    private var eventSink: EventChannel.EventSink? = null

    val ready: Boolean get() = embedded != null

    private fun loadProvider(): EmbeddedChromiumEngine? = try {
        val clazz = Class.forName(PROVIDER_CLASS)
        val instance = clazz.getConstructor(Activity::class.java)
            .newInstance(activity)
        instance as? EmbeddedChromiumEngine
    } catch (_: ReflectiveOperationException) {
        null
    } catch (_: ClassCastException) {
        null
    } catch (_: LinkageError) {
        null
    }

    private fun emit(event: Map<String, Any?>) {
        activity.runOnUiThread { eventSink?.success(event) }
    }

    fun register(engine: FlutterEngine) {
        EventChannel(engine.dartExecutor.binaryMessenger, EVENT_CHANNEL)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    eventSink = events
                }

                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            })

        engine.platformViewsController.registry.registerViewFactory(
            VIEW_ID,
            object : PlatformViewFactory(StandardMessageCodec.INSTANCE) {
                override fun create(
                    context: Context,
                    viewId: Int,
                    args: Any?
                ): PlatformView {
                    val parameters = args as? Map<*, *> ?: emptyMap<String, Any>()
                    val tabId = (parameters["tabId"] as? Number)?.toInt() ?: -1
                    val url = parameters["initialUrl"] as? String ?: "about:blank"
                    val surface = if (embedded != null && tabId >= 0) {
                        embedded.createPage(context, tabId, url, ::emit)
                    } else {
                        TextView(context).apply {
                            text = "Chromium native engine not installed. " +
                                "Android WebView is not a substitute for Chrome extensions."
                        }
                    }
                    return object : PlatformView {
                        override fun getView(): View = surface

                        override fun dispose() {
                            if (tabId >= 0) embedded?.closePage(tabId)
                        }
                    }
                }
            }
        )

        MethodChannel(engine.dartExecutor.binaryMessenger, NAVIGATION_CHANNEL)
            .setMethodCallHandler { call, result ->
                if (call.method == "status") {
                    result.success(
                        mapOf(
                            "engine" to if (ready) "chromium-native" else "missing",
                            "embedded" to ready
                        )
                    )
                    return@setMethodCallHandler
                }
                val provider = embedded
                if (provider == null) {
                    result.error(
                        "CHROMIUM_NOT_INSTALLED",
                        "An in-app Chromium extension engine is required.",
                        null
                    )
                    return@setMethodCallHandler
                }
                val tabId = call.argument<Int>("tabId")
                if (tabId == null || tabId < 0) {
                    result.error("BAD_TAB_ID", "tabId must be nonnegative", null)
                    return@setMethodCallHandler
                }
                try {
                    val arguments = call.arguments as? Map<*, *> ?: emptyMap<String, Any>()
                    val params = arguments.entries.associate {
                        it.key.toString() to it.value
                    }
                    result.success(provider.invoke(tabId, call.method, params))
                } catch (error: Exception) {
                    result.error("CHROMIUM_COMMAND_FAILED", error.message, null)
                }
            }

        MethodChannel(engine.dartExecutor.binaryMessenger, EXTENSION_CHANNEL)
            .setMethodCallHandler { call, result ->
                val provider = embedded
                if (provider == null) {
                    when (call.method) {
                        "capabilities" -> result.success(
                            mapOf(
                                "engine" to "chromium-unavailable",
                                "nativeEngine" to false,
                                "manifestV3" to false,
                                "declarativeNetRequest" to false,
                                "serviceWorkers" to false,
                                "permissionPrompts" to false,
                                "chromeWebStoreInstall" to false,
                                "actionPopup" to false
                            )
                        )
                        "isInstalledAndEnabled" -> result.success(false)
                        else -> result.error(
                            "CHROMIUM_NOT_INSTALLED",
                            "Chrome Web Store extensions require a native Chromium engine.",
                            null
                        )
                    }
                    return@setMethodCallHandler
                }
                try {
                    val arguments = call.arguments as? Map<*, *> ?: emptyMap<String, Any>()
                    val params = arguments.entries.associate {
                        it.key.toString() to it.value
                    }
                    if (call.method == "capabilities") {
                        result.success(provider.capabilities())
                    } else {
                        result.success(provider.extensions(call.method, params))
                    }
                } catch (error: Exception) {
                    result.error("CHROMIUM_EXTENSION_FAILED", error.message, null)
                }
            }
    }

    fun dispose() {
        eventSink = null
    }
}
