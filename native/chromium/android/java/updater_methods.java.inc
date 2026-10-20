    @CalledByNative
    private static @JniType("std::string") String getInternetBrowserUpdateDirectory() {
        return new java.io.File(ContextUtils.getApplicationContext().getCacheDir(),
                "internet-browser-updates").getAbsolutePath();
    }

    @CalledByNative
    private static boolean openInternetBrowserInstaller(@JniType("std::string") String path) {
        Context context = ContextUtils.getApplicationContext();
        try {
            java.io.File file = new java.io.File(path).getCanonicalFile();
            String directory = new java.io.File(context.getCacheDir(),
                    "internet-browser-updates").getCanonicalPath() + java.io.File.separator;
            if (!file.getPath().startsWith(directory) || !file.getName().endsWith(".apk")) return false;
            android.content.pm.PackageInfo archive = context.getPackageManager()
                    .getPackageArchiveInfo(file.getPath(), 0);
            if (archive == null || !context.getPackageName().equals(archive.packageName)) return false;
            if (!context.getPackageManager().canRequestPackageInstalls()) return false;
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(ChromeFileProvider.generateUri(file),
                    "application/vnd.android.package-archive");
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            context.startActivity(intent);
            return true;
        } catch (java.io.IOException | IllegalArgumentException | SecurityException | ActivityNotFoundException error) {
            return false;
        }
    }

    @CalledByNative
    private static boolean openInternetBrowserInstallSettings() {
        Context context = ContextUtils.getApplicationContext();
        try {
            Intent intent = new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + context.getPackageName()));
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            return true;
        } catch (SecurityException | ActivityNotFoundException error) {
            return false;
        }
    }
