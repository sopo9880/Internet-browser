#include <cassert>
#include <string>
#include "native/chromium/common/overlay/video_payload.h"
int main() {
  using internet_browser::VideoPayloadExtension;
  using internet_browser::IsVideoErrorMime;
  assert(VideoPayloadExtension("<!doctype html><html>login</html>").empty());
  assert(VideoPayloadExtension("{\"error\":\"access denied\"}").empty());
  assert(VideoPayloadExtension("ftyp").empty());
  assert(VideoPayloadExtension(std::string(4, '\0') + "ftypisom" + std::string(20, '\0')) == ".mp4");
  assert(VideoPayloadExtension(std::string("\x1a\x45\xdf\xa3", 4) + std::string(28, '\0')).empty());
  assert(VideoPayloadExtension(std::string("\x1a\x45\xdf\xa3", 4) + "headerwebmtype" + std::string(20, '\0')) == ".webm");
  assert(VideoPayloadExtension(std::string("\x1a\x45\xdf\xa3", 4) + "headermatroskatype") == ".mkv");
  assert(VideoPayloadExtension("RIFF1234AVI LISTpayload") == ".avi");
  assert(VideoPayloadExtension("RIFF1234WAVEdata123456").empty());
  assert(IsVideoErrorMime("text/html"));
  assert(IsVideoErrorMime("application/json; charset=utf-8"));
  assert(!IsVideoErrorMime("video/mp4"));
  assert(!IsVideoErrorMime("application/octet-stream"));
  assert(!IsVideoErrorMime("text/plain"));  // Real bytes decide ambiguous MIME.
}
