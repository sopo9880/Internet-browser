#!/usr/bin/env python3
"""Configure signing only inside a trusted GitHub main-branch release runner.

No signing credential is written to source control. Base64 is decoded to the
runner's private temporary directory. PR builds use this script ONLY in
--validate-template mode (which does not read credentials).
"""
import argparse
import base64
import binascii
import os
from pathlib import Path


SIGNING_CONFIG = '''
    signingConfigs {
        create("release") {
            val releaseKeyFile = System.getenv("ANDROID_RELEASE_KEYSTORE_FILE")
                ?: throw GradleException("Missing release keystore path")
            storeFile = file(releaseKeyFile)
            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                ?: throw GradleException("Missing keystore password")
            keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                ?: throw GradleException("Missing key alias")
            keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
                ?: throw GradleException("Missing key password")
            storeType = "PKCS12"
        }
    }

'''


def patch_gradle(source: str) -> str:
    """Replace the Flutter template's debug release config, failing closed."""
    opening = "android {\n"
    debug = 'signingConfig = signingConfigs.getByName("debug")'
    if source.count(opening) != 1 or source.count(debug) != 1:
        raise ValueError(
            "Unsupported Flutter Android Gradle template: refusing to sign"
        )
    if "ANDROID_RELEASE_KEYSTORE_FILE" in source:
        raise ValueError("Release signing is already configured")
    source = source.replace(opening, opening + SIGNING_CONFIG, 1)
    return source.replace(
        debug, 'signingConfig = signingConfigs.getByName("release")', 1
    )


def decode_key(encoded: str) -> bytes:
    """Only accept a nonempty base64 PKCS12 file, never silently generate keys."""
    try:
        binary = base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("ANDROID_KEYSTORE_BASE64 is not valid base64") from exc
    if len(binary) < 128 or binary[0] != 0x30:
        raise ValueError("Expected a PKCS12 (.p12) keystore, not a text file")
    return binary


def configure(
    gradle_path: Path,
    *,
    env: dict[str, str],
    write: bool,
) -> Path | None:
    source = gradle_path.read_text(encoding="utf-8")
    patched = patch_gradle(source)

    if not write:
        return None

    names = (
        "ANDROID_KEYSTORE_BASE64",
        "ANDROID_KEYSTORE_PASSWORD",
        "ANDROID_KEY_ALIAS",
        "ANDROID_KEY_PASSWORD",
    )
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise ValueError("Missing GitHub Actions secrets: " + ", ".join(missing))
    temp = env.get("RUNNER_TEMP")
    if not temp:
        raise ValueError("RUNNER_TEMP is required for release signing")

    key_path = Path(temp) / "internet-browser-release.p12"
    if key_path.exists():
        raise ValueError("Refusing to overwrite an existing release keystore")
    encoded = decode_key(env["ANDROID_KEYSTORE_BASE64"])
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with key_path.open("xb") as file:
            file.write(encoded)
        key_path.chmod(0o600)
        gradle_path.write_text(patched, encoding="utf-8")
    except Exception:
        key_path.unlink(missing_ok=True)
        raise
    return key_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gradle-file", default="android/app/build.gradle.kts"
    )
    parser.add_argument(
        "--write", action="store_true", help="Decode secrets and patch Gradle"
    )
    args = parser.parse_args()
    destination = configure(Path(args.gradle_file), env=dict(os.environ), write=args.write)
    if destination is None:
        print("Generated Gradle signing template is compatible (no secrets used).")
    else:
        print("Release PKCS12 signing configured in private runner temp storage.")


if __name__ == "__main__":
    main()
