#include <cassert>
#include <iostream>
#include "native/chromium/common/overlay/update_validation.h"
int main() {
  using namespace internet_browser;
  assert(UpdateVersion("v0.2.10") > UpdateVersion("0.2.9"));
  assert(UpdateVersion("0.2.2") == UpdateVersion("0.2.2.0"));
  for (const auto* value : {"", "v1.2", "1.2.3.4.5", "1..2.3", "1.2.3.", "1.2.3-beta", "1.2.-3", "1.2.4294967296", "V1.2.3", "1.2.3/path", " 1.2.3"})
    assert(!UpdateVersion(value));
  const std::string tag = "v0.3.0";
  const std::string name = "Internet-browser-Windows-Setup-v0.3.0.exe";
  const std::string url = "https://github.com/sopo9880/Internet-browser/releases/download/" + tag + "/" + name;
  const std::string hash = "sha256:" + std::string(64, 'a');
  assert(ValidUpdateAsset(tag, name, url, 123, hash, false));
  assert(!ValidUpdateAsset(tag, name, url, 123, hash, true));
  assert(!ValidUpdateAsset(tag, name, url + "?host=evil", 123, hash, false));
  assert(!ValidUpdateAsset(tag, name, "http" + url.substr(5), 123, hash, false));
  assert(!ValidUpdateAsset(tag, name, "https://github.com@evil.example/file.exe", 123, hash, false));
  assert(!ValidUpdateAsset(tag, "../" + name, url, 123, hash, false));
  assert(!ValidUpdateAsset(tag, name, url, 0, hash, false));
  assert(!ValidUpdateAsset(tag, name, url, kMaxInstallerBytes + 1LL, hash, false));
  assert(!ValidUpdateAsset(tag, name, url, 123, "sha256:" + std::string(64, 'g'), false));
  assert(!ValidUpdateAsset(tag, name, url, 123, "", false));
  const std::string apk = "Internet-browser-Android-v0.3.0.apk";
  assert(ValidUpdateAsset(tag, apk, "https://github.com/sopo9880/Internet-browser/releases/download/" + tag + "/" + apk, 123, hash, true));
  // "가" is 3 UTF-8 bytes; a cut inside it must drop the whole character.
  const std::string korean = "ab\xea\xb0\x80" "cd";
  assert(TruncateUtf8(korean, 100) == korean);
  assert(TruncateUtf8(korean, 5) == "ab\xea\xb0\x80");
  assert(TruncateUtf8(korean, 4) == "ab");
  assert(TruncateUtf8(korean, 3) == "ab");
  assert(TruncateUtf8(korean, 2) == "ab");
  assert(TruncateUtf8(korean, 0).empty());
  assert(TruncateUtf8(std::string(70000, 'x'), 65536).size() == 65536);
  std::cout << "Native update version and trusted-asset checks passed.\n";
}
