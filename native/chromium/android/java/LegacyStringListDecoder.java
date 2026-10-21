package org.chromium.chrome.browser;

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** Bounded reader for Flutter's legacy serialized string-list format.
 *
 * This reads the two supported Java serialization layouts directly. It never
 * instantiates serialized classes or invokes ObjectInputStream/readObject.
 */
final class LegacyStringListDecoder {
    private final DataInputStream input;
    private final Map<Integer, Object> handles = new HashMap<>();
    private int nextHandle = 0x7e0000;
    private static final int MAX_COUNT = 10000;

    private LegacyStringListDecoder(byte[] data) throws IOException {
        if (data.length > 1024 * 1024) throw new IOException("Legacy list exceeds limit");
        input = new DataInputStream(new ByteArrayInputStream(data));
    }

    static List<String> decode(byte[] data) throws IOException {
        return new LegacyStringListDecoder(data).read();
    }

    private void expect(int value) throws IOException {
        if (input.readUnsignedByte() != value) throw new IOException("Unsupported legacy list layout");
    }

    private String utf(int maximum) throws IOException {
        int length = input.readUnsignedShort();
        if (length > maximum) throw new IOException("Legacy string exceeds limit");
        byte[] encoded = new byte[length + 2];
        encoded[0] = (byte) (length >>> 8);
        encoded[1] = (byte) length;
        input.readFully(encoded, 2, length);
        return new DataInputStream(new ByteArrayInputStream(encoded)).readUTF();
    }

    private String string(int maximum) throws IOException {
        int tag = input.readUnsignedByte();
        if (tag == 0x70) return null;
        if (tag == 0x74) {
            String value = utf(maximum);
            handles.put(nextHandle++, value);
            return value;
        }
        if (tag == 0x71) {
            Object value = handles.get(input.readInt());
            if (!(value instanceof String) || ((String) value).length() > maximum)
                throw new IOException("Invalid legacy string reference");
            return (String) value;
        }
        throw new IOException("Legacy list contains a non-string object");
    }

    private String descriptor() throws IOException {
        expect(0x72);
        String name = utf(128);
        if (!name.equals("java.util.ArrayList") && !name.equals("java.util.Arrays$ArrayList")
                && !name.equals("[Ljava.lang.String;"))
            throw new IOException("Unsupported legacy class");
        input.readLong(); // Serial version UID is data, never a class lookup.
        handles.put(nextHandle++, new Object());
        int flags = input.readUnsignedByte();
        int count = input.readUnsignedShort();
        if (name.equals("java.util.ArrayList")) {
            if (flags != 3 || count != 1) throw new IOException("Invalid ArrayList descriptor");
            expect('I');
            if (!utf(16).equals("size")) throw new IOException("Invalid ArrayList field");
        } else if (name.equals("java.util.Arrays$ArrayList")) {
            if (flags != 2 || count != 1) throw new IOException("Invalid Arrays list descriptor");
            expect('[');
            if (!utf(16).equals("a")) throw new IOException("Invalid legacy array field");
            String arrayType = string(128);
            if (!"[Ljava/lang/Object;".equals(arrayType) && !"[Ljava/lang/String;".equals(arrayType))
                throw new IOException("Unsupported legacy array type");
        } else if (flags != 2 || count != 0) {
            throw new IOException("Invalid String array descriptor");
        }
        expect(0x78); // End of class annotations.
        expect(0x70); // No superclass.
        return name;
    }

    private int count() throws IOException {
        int count = input.readInt();
        if (count < 0 || count > MAX_COUNT) throw new IOException("Legacy list count exceeds limit");
        return count;
    }

    private List<String> read() throws IOException {
        if (input.readUnsignedShort() != 0xaced || input.readUnsignedShort() != 5)
            throw new IOException("Invalid serialization header");
        expect(0x73);
        String type = descriptor();
        if (type.equals("[Ljava.lang.String;")) throw new IOException("Expected list, not array");
        handles.put(nextHandle++, new Object());
        int size;
        if (type.equals("java.util.ArrayList")) {
            size = count();
            expect(0x77);
            expect(4);
            if (count() != size) throw new IOException("Legacy list sizes differ");
        } else {
            expect(0x75);
            if (!descriptor().equals("[Ljava.lang.String;")) throw new IOException("Expected string array");
            handles.put(nextHandle++, new Object());
            size = count();
        }
        List<String> result = new ArrayList<>(size);
        for (int i = 0; i < size; i++) result.add(string(32768));
        if (type.equals("java.util.ArrayList")) expect(0x78);
        if (input.available() != 0) throw new IOException("Unexpected trailing serialization data");
        return result;
    }
}
