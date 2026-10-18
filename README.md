# Internet-browser

Windows + Android Flutter browser, version 0.1.0 development.

Current scope: WebView-based tab navigation, history/bookmarks, basic host-based ad blocking, direct MP4/WebM/MOV/M4V detection, and offline video files (opened with system player).

**Not yet implemented:** GoodbyeDPI/ByeDPI transport integration, full EasyList engine, DRM/streaming video extraction, persistent background downloads, production Android signing and automatic release publication. The DPI settings screen explicitly states that bypass is not operating.

To develop locally, install Flutter 3.35.7 and appropriate Android or Windows native SDK:

    flutter create --project-name=internet_browser --org=io.github.sopo9880 --platforms=android,windows .
    python tool/prepare_platforms.py
    flutter pub get
    dart format lib test
    flutter analyze
    flutter test

Run Windows: flutter build windows --release
Run Android: flutter build apk --release

CI creates unsigned test artifacts. Production release must wait for CI checks, real-device evaluation and an explicit release command. Keep versions in the 0.x series.

Update checks, seven-day snooze, verified installer download and user-confirmed update installation are implemented; see docs/UPDATES.md. The Windows CI additionally creates an Inno Setup installer. The Android CI build is unsigned for production purposes; stable Android release signing is mandatory before publishing an update.
