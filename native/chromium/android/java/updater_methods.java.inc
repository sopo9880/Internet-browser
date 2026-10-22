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
            intent.setDataAndType(ChromeFileProvider.generateUri(file),
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
    private static boolean showInternetBrowserUpdateFile(@JniType("std::string") String path) {
        Context context = ContextUtils.getApplicationContext();
        android.content.ContentResolver resolver = context.getContentResolver();
        Uri pending = null;
        try {
            java.io.File file = new java.io.File(path).getCanonicalFile();
            String directory = new java.io.File(context.getCacheDir(),
                    "internet-browser-updates").getCanonicalPath() + java.io.File.separator;
            if (!file.getPath().startsWith(directory) || !file.isFile()
                    || !file.getName().endsWith(".apk")) return false;
            String savedPath = ContextUtils.getAppSharedPreferences().getString(
                    "internet_browser_update_export_path", "");
            String savedUri = ContextUtils.getAppSharedPreferences().getString(
                    "internet_browser_update_export_uri", "");
            boolean exists = false;
            if (file.getPath().equals(savedPath) && !savedUri.isEmpty()) {
                try (android.os.ParcelFileDescriptor handle = resolver.openFileDescriptor(
                        Uri.parse(savedUri), "r")) {
                    exists = handle != null && handle.getStatSize() == file.length();
                } catch (java.io.IOException | SecurityException ignored) { }
            }
            if (!exists) {
                android.content.ContentValues values = new android.content.ContentValues();
                values.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, file.getName());
                values.put(android.provider.MediaStore.MediaColumns.MIME_TYPE,
                        "application/vnd.android.package-archive");
                values.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH,
                        android.os.Environment.DIRECTORY_DOWNLOADS + "/Internet Browser");
                values.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 1);
                pending = resolver.insert(android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (pending == null) return false;
                try (java.io.InputStream input = new java.io.FileInputStream(file);
                        java.io.OutputStream output = resolver.openOutputStream(pending)) {
                    if (output == null) throw new java.io.IOException("No output stream");
                    byte[] buffer = new byte[65536];
                    int length;
                    while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
                }
                values.clear(); values.put(android.provider.MediaStore.MediaColumns.IS_PENDING, 0);
                if (resolver.update(pending, values, null, null) != 1)
                    throw new java.io.IOException("Could not publish APK copy");
                ContextUtils.getAppSharedPreferences().edit()
                        .putString("internet_browser_update_export_path", file.getPath())
                        .putString("internet_browser_update_export_uri", pending.toString()).apply();
                pending = null;
            }
            context.startActivity(new Intent(android.app.DownloadManager.ACTION_VIEW_DOWNLOADS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            return true;
        } catch (java.io.IOException | IllegalArgumentException | SecurityException
                | ActivityNotFoundException error) {
            if (pending != null) {
                try { resolver.delete(pending, null, null); }
                catch (SecurityException | IllegalArgumentException ignored) { }
            }
            return false;
        }
    }
