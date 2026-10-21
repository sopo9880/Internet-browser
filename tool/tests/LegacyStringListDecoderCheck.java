package org.chromium.chrome.browser;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Interoperability checks against Java's actual serialization implementation. */
public final class LegacyStringListDecoderCheck {
    private static byte[] encode(Object value) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (ObjectOutputStream stream = new ObjectOutputStream(output)) {
            stream.writeObject(value);
        }
        return output.toByteArray();
    }

    private static void rejected(byte[] bytes) throws IOException {
        try {
            LegacyStringListDecoder.decode(bytes);
        } catch (IOException expected) {
            return;
        }
        throw new AssertionError("Unsupported or malformed data was accepted");
    }

    public static void main(String[] args) throws IOException {
        String shared = "https://example.org/한글";
        List<String> values = Arrays.asList(shared, "https://example.com/", shared, null);
        for (List<String> original : Arrays.asList(values, new ArrayList<>(values), new ArrayList<String>())) {
            if (!original.equals(LegacyStringListDecoder.decode(encode(original))))
                throw new AssertionError("Existing serialized list changed");
        }
        rejected(encode(Arrays.asList(1, 2)));
        rejected(encode(new java.util.Date()));
        rejected(new byte[] {(byte) 0xac, (byte) 0xed});
        byte[] oversized = encode(new ArrayList<>(values));
        for (int i = 0; i < oversized.length - 6; i++) {
            if (oversized[i] == 0x77 && oversized[i + 1] == 4) {
                Arrays.fill(oversized, i + 2, i + 6, (byte) 0x7f);
                break;
            }
        }
        rejected(oversized);
        System.out.println("Legacy Java string-list interoperability and rejection checks passed");
    }
}
