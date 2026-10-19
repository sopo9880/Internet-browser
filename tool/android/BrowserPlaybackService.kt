package io.github.sopo9880.internet_browser

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.IBinder

/// Foreground notification/media session for a Flutter media_kit player.
/// Native actions forward to the Flutter player; they do not start a
/// second independent decoder. This keeps the playback UI synchronized.
class BrowserPlaybackService : Service() {
    companion object {
        const val ACTION_UPDATE = "browser.playback.UPDATE"
        private const val ACTION_PLAY = "browser.playback.PLAY"
        private const val ACTION_PAUSE = "browser.playback.PAUSE"
        private const val CHANNEL = "internet_browser_playback"
        private const val NOTIFICATION_ID = 4512
    }

    private var session: MediaSession? = null
    private var title = "오프라인 동영상"
    private var playing = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val notifications = getSystemService(NotificationManager::class.java)
        notifications.createNotificationChannel(
            NotificationChannel(
                CHANNEL,
                "동영상 백그라운드 재생",
                NotificationManager.IMPORTANCE_LOW
            )
        )
        session = MediaSession(this, "Internet-browser")
        session?.setCallback(object : MediaSession.Callback() {
            override fun onPlay() {
                MainActivity.callback?.invokeMethod("play", null)
            }
            override fun onPause() {
                MainActivity.callback?.invokeMethod("pause", null)
            }
        })
        session?.isActive = true
    }

    private fun actionPending(action: String, code: Int): PendingIntent =
        PendingIntent.getService(
            this, code,
            Intent(this, BrowserPlaybackService::class.java).setAction(action),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

    private fun updateNotification() {
        session?.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .build()
        )
        session?.setPlaybackState(
            PlaybackState.Builder()
                .setActions(
                    PlaybackState.ACTION_PLAY or
                    PlaybackState.ACTION_PAUSE or
                    PlaybackState.ACTION_PLAY_PAUSE
                )
                .setState(
                    if (playing) PlaybackState.STATE_PLAYING
                    else PlaybackState.STATE_PAUSED,
                    PlaybackState.PLAYBACK_POSITION_UNKNOWN,
                    if (playing) 1f else 0f
                )
                .build()
        )
        val open = PendingIntent.getActivity(
            this, 1,
            Intent(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val pauseOrPlay = if (playing) ACTION_PAUSE else ACTION_PLAY
        val buttonIcon = if (playing) android.R.drawable.ic_media_pause
                         else android.R.drawable.ic_media_play
        val notification = Notification.Builder(this, CHANNEL)
            .setContentTitle(title)
            .setContentText("Internet Browser · 오프라인 재생")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(open)
            .setOngoing(playing)
            .addAction(
                Notification.Action.Builder(
                    buttonIcon,
                    if (playing) "일시정지" else "재생",
                    actionPending(pauseOrPlay, 2)
                ).build()
            )
            .setStyle(
                Notification.MediaStyle()
                    .setMediaSession(session?.sessionToken)
                    .setShowActionsInCompactView(0)
            )
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                NOTIFICATION_ID, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            )
        } else startForeground(NOTIFICATION_ID, notification)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_PLAY -> {
                playing = true
                MainActivity.callback?.invokeMethod("play", null)
            }
            ACTION_PAUSE -> {
                playing = false
                MainActivity.callback?.invokeMethod("pause", null)
            }
            ACTION_UPDATE -> {
                playing = intent.getBooleanExtra("playing", false)
                title = intent.getStringExtra("title") ?: title
            }
        }
        updateNotification()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        session?.release()
        session = null
        super.onDestroy()
    }
}
