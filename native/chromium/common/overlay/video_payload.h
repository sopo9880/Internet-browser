#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PAYLOAD_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PAYLOAD_H_
#include <string_view>
namespace internet_browser {
// Check downloaded bytes, never a URL extension or server-suggested filename.
// MP4 structural/encryption validation is performed separately by ClearMp4.
inline std::string_view VideoPayloadExtension(std::string_view bytes) {
  if (bytes.size() < 16) return {};
  if (bytes.substr(4, 4) == "ftyp") return ".mp4";
  if (bytes.substr(0, 4) == std::string_view("\x1a\x45\xdf\xa3", 4)) {
    if (bytes.find("webm") != std::string_view::npos) return ".webm";
    if (bytes.find("matroska") != std::string_view::npos) return ".mkv";
    return {};
  }
  if (bytes.substr(0, 4) == "RIFF" && bytes.substr(8, 4) == "AVI ") return ".avi";
  if (bytes.substr(0, 3) == "FLV" && bytes[3] == 1) return ".flv";
  return {};
}
inline bool IsVideoErrorMime(std::string_view mime) {
  return mime.starts_with("text/html") || mime.starts_with("application/json") ||
      mime.starts_with("application/xhtml") || mime.starts_with("application/xml");
}
}
#endif
