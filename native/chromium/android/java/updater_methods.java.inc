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
                    .getPackageArchiveInfo(file.getPath(), android.content.pm.PackageManager.GET_SIGNING_CERTIFICATES);
            if (archive == null || !context.getPackageName().equals(archive.packageName)) return false;
            android.content.pm.PackageInfo installed = context.getPackageManager().getPackageInfo(
                    context.getPackageName(), android.content.pm.PackageManager.GET_SIGNING_CERTIFICATES);
            if (archive.getLongVersionCode() <= installed.getLongVersionCode()
                    || archive.signingInfo == null || installed.signingInfo == null) return false;
            java.util.Set<android.content.pm.Signature> incoming = new java.util.HashSet<>(
                    java.util.Arrays.asList(archive.signingInfo.getApkContentsSigners()));
            java.util.Set<android.content.pm.Signature> current = new java.util.HashSet<>(
                    java.util.Arrays.asList(installed.signingInfo.getApkContentsSigners()));
            if (incoming.isEmpty() || !incoming.equals(current)) return false;
            if (!context.getPackageManager().canRequestPackageInstalls()) return false;
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(exportInternetBrowserUpdateFile(file),
                    "application/vnd.android.package-archive");
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            context.startActivity(intent);
            return true;
        } catch (java.io.IOException | android.content.pm.PackageManager.NameNotFoundException
                | IllegalArgumentException | SecurityException | ActivityNotFoundException error) {
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

    @CalledByNative
    private static boolean openInternetBrowserSecuritySettings() {
        Context context = ContextUtils.getApplicationContext();
        for (String action : new String[] {
                android.provider.Settings.ACTION_SECURITY_SETTINGS,
                android.provider.Settings.ACTION_SETTINGS}) {
            try {
                context.startActivity(new Intent(action).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                return true;
            } catch (SecurityException | ActivityNotFoundException error) {
                // Some devices expose security only through the main settings screen.
            }
        }
        return false;
    }

    @CalledByNative
    private static boolean openInternetBrowserBrowserSettings() {
        Context context = ContextUtils.getApplicationContext();
        try {
            Intent intent = new Intent();
            intent.setClassName(context, "org.chromium.chrome.browser.settings.SettingsActivity");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            return true;
        } catch (SecurityException | ActivityNotFoundException error) {
            return false;
        }
    }

    // Both Install and Open location use the same public Downloads APK.
    // Recheck bytes when reusing a URI: public files can be modified externally.
    private static byte[] internetBrowserUpdateDigest(java.io.InputStream input) throws java.io.IOException {
        try {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            int length;
            while ((length = input.read(buffer)) != -1) digest.update(buffer, 0, length);
            return digest.digest();
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new java.io.IOException(error);
        }
    }

    private static boolean sameInternetBrowserUpdateFile(java.io.File file, Uri uri) {
        try (java.io.InputStream original = new java.io.FileInputStream(file);
                java.io.InputStream exported = ContextUtils.getApplicationContext()
                        .getContentResolver().openInputStream(uri)) {
            if (exported == null) return false;
            return java.util.Arrays.equals(internetBrowserUpdateDigest(original),
                    internetBrowserUpdateDigest(exported));
        } catch (java.io.IOException | SecurityException | IllegalArgumentException error) {
            return false;
        }
    }

    private static synchronized Uri exportInternetBrowserUpdateFile(java.io.File file) throws java.io.IOException {
        Context context = ContextUtils.getApplicationContext();
        String directory = new java.io.File(context.getCacheDir(),
                "internet-browser-updates").getCanonicalPath() + java.io.File.separator;
        file = file.getCanonicalFile();
        if (!file.getPath().startsWith(directory) || !file.isFile()
                || !file.getName().endsWith(".apk")) throw new java.io.IOException("Invalid APK path");
        String savedPath = ContextUtils.getAppSharedPreferences().getString(
                "internet_browser_update_export_path", "");
        String savedUri = ContextUtils.getAppSharedPreferences().getString(
                "internet_browser_update_export_uri", "");
        if (file.getPath().equals(savedPath) && !savedUri.isEmpty()) {
            Uri uri = Uri.parse(savedUri);
            if (sameInternetBrowserUpdateFile(file, uri)) return uri;
        }
        android.content.ContentResolver resolver = context.getContentResolver();
        android.content.ContentValues values = new android.content.ContentValues();
        values.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, file.getName());
        values.put(android.provider.MediaStore.MediaColumns.MIME_TYPE,
                "application/vnd.android.package-archive");
        values.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH,
                android.os.Environment.DIRECTORY_DOWNLOADS + "/Internet Browser");
        values.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 1);
        Uri pending = resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (pending == null) throw new java.io.IOException("Could not create APK copy");
        boolean published = false;
        try {
            try (java.io.InputStream input = new java.io.FileInputStream(file);
                    java.io.OutputStream output = resolver.openOutputStream(pending)) {
                if (output == null) throw new java.io.IOException("No output stream");
                byte[] buffer = new byte[65536];
                int length;
                while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
            }
            if (!sameInternetBrowserUpdateFile(file, pending))
                throw new java.io.IOException("Exported APK differs");
            values.clear(); values.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 0);
            if (resolver.update(pending, values, null, null) != 1)
                throw new java.io.IOException("Could not publish APK copy");
            ContextUtils.getAppSharedPreferences().edit()
                    .putString("internet_browser_update_export_path", file.getPath())
                    .putString("internet_browser_update_export_uri", pending.toString()).apply();
            published = true;
            return pending;
        } finally {
            if (!published) resolver.delete(pending, null, null);
        }
    }

    @CalledByNative
    private static boolean showInternetBrowserUpdateFile(@JniType("std::string") String path) {
        try {
            exportInternetBrowserUpdateFile(new java.io.File(path));
            ContextUtils.getApplicationContext().startActivity(
                    new Intent(android.app.DownloadManager.ACTION_VIEW_DOWNLOADS)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return true;
        } catch (java.io.IOException | IllegalArgumentException | SecurityException
                | ActivityNotFoundException error) {
            return false;
        }
    }
