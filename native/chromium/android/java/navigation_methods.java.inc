    private static final String INTERNET_BROWSER_BLOCK_EXTERNAL_APPS =
            "internet_browser.block_external_apps";

    @CalledByNative
    public static boolean getInternetBrowserBlockExternalApps() {
        return ContextUtils.getAppSharedPreferences().getBoolean(
                INTERNET_BROWSER_BLOCK_EXTERNAL_APPS, true);
    }

    @CalledByNative
    private static void setInternetBrowserBlockExternalApps(boolean blocked) {
        ContextUtils.getAppSharedPreferences().edit()
                .putBoolean(INTERNET_BROWSER_BLOCK_EXTERNAL_APPS, blocked).apply();
    }

    public static boolean shouldBlockInternetBrowserExternalApp(String scheme) {
        // Include custom app schemes (for example vnd.youtube:), not only
        // App Links and intent:. Explicit communication links stay usable.
        if (!getInternetBrowserBlockExternalApps() || scheme == null) return false;
        switch (scheme) {
            case "":
            case "tel":
            case "mailto":
            case "sms":
            case "smsto":
            case "content":
            case "file":
            case "about":
            case "chrome":
            case "chrome-native":
            case "data":
            case "javascript":
            case "blob":
                return false;
            default:
                return true;
        }
    }
