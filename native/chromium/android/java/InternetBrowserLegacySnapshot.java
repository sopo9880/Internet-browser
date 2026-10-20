package org.chromium.chrome.browser;

import android.content.Context;
import android.util.AtomicFile;
import android.util.Log;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.json.JSONArray;
import org.json.JSONObject;

/** Read-only migration snapshot. Original Flutter preferences are never edited. */
final class InternetBrowserLegacySnapshot {
    // SharedPreferences Android's documented legacy and JSON-list markers.
    private static final String LIST_PREFIX = "VGhpcyBpcyB0aGUgcHJlZml4IGZvciBhIGxpc3Qu";

    private static JSONArray strings(Object value) throws Exception {
        JSONArray values = new JSONArray();
        if (value instanceof Set<?>) {
            for (Object item : (Set<?>) value) values.put(item);
        } else if (value instanceof String) {
            String encoded = (String) value;
            if (encoded.length() > 1500000) throw new IOException("Legacy list exceeds limit");
            if (encoded.startsWith(LIST_PREFIX + "!")) {
                values = new JSONArray(encoded.substring(LIST_PREFIX.length() + 1));
            } else if (encoded.startsWith(LIST_PREFIX)) {
                List<String> decoded = LegacyStringListDecoder.decode(
                        Base64.getMimeDecoder().decode(encoded.substring(LIST_PREFIX.length())));
                for (String item : decoded) values.put(item);
            }
        }
        if (values.length() > 10000) throw new IOException("Legacy list count exceeds limit");
        JSONArray result = new JSONArray();
        Set<String> seen = new LinkedHashSet<>();
        for (int i = 0; i < values.length(); i++) {
            Object valueAtIndex = values.opt(i);
            if (valueAtIndex instanceof String && ((String) valueAtIndex).length() <= 8192
                    && seen.add((String) valueAtIndex)) result.put(valueAtIndex);
        }
        return result;
    }

    static void prepare(Context context) {
        AtomicFile atomic = null;
        FileOutputStream output = null;
        try {
            File original = new File(context.getApplicationInfo().dataDir,
                    "shared_prefs/FlutterSharedPreferences.xml");
            if (!original.isFile()) return;
            if (original.length() > 4 * 1024 * 1024) throw new IOException("Legacy preferences exceed limit");
            File snapshot = new File(context.getDir("chrome", Context.MODE_PRIVATE),
                    "internet-browser-legacy.json");
            if (snapshot.isFile() && snapshot.lastModified() >= original.lastModified()) return;
            Map<String, ?> values = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE).getAll();
            JSONObject normalized = new JSONObject();
            normalized.put("found", true);
            normalized.put("bookmarks", strings(values.get("flutter.bookmarks")));
            normalized.put("history", strings(values.get("flutter.history")));
            JSONObject settings = new JSONObject();
            int count = 0;
            for (Map.Entry<String, ?> entry : values.entrySet()) {
                if (++count > 1024) throw new IOException("Legacy preference count exceeds limit");
                String key = entry.getKey();
                if (!key.startsWith("flutter.") || key.equals("flutter.bookmarks") || key.equals("flutter.history")) continue;
                Object value = entry.getValue();
                if (value instanceof Boolean || value instanceof Number) {
                    settings.put(key.substring(8), value);
                } else if (value instanceof String && ((String) value).startsWith(LIST_PREFIX)) {
                    settings.put(key.substring(8), strings(value));
                } else if (value instanceof String && ((String) value).length() <= 8192) {
                    settings.put(key.substring(8), value);
                }
            }
            normalized.put("settings", settings);
            normalized.put("snapshot_version", 1);
            byte[] bytes = normalized.toString().getBytes(StandardCharsets.UTF_8);
            if (bytes.length > 4 * 1024 * 1024) throw new IOException("Legacy snapshot exceeds limit");
            atomic = new AtomicFile(snapshot);
            output = atomic.startWrite();
            output.write(bytes);
            atomic.finishWrite(output);
            output = null;
        } catch (Exception error) {
            if (atomic != null && output != null) atomic.failWrite(output);
            // Never log bookmarks, browsing history or encoded preference data.
            Log.w("InternetBrowser", "Legacy snapshot unavailable: " + error.getClass().getSimpleName());
        }
    }
}
