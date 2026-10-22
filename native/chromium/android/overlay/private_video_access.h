#ifndef CHROME_BROWSER_INTERNET_BROWSER_PRIVATE_VIDEO_ACCESS_H_
#define CHROME_BROWSER_INTERNET_BROWSER_PRIVATE_VIDEO_ACCESS_H_
#include <string_view>
#include "video_file_types.h"

namespace internet_browser {
// Relative to the current profile. Never admit profile databases or metadata.
inline bool IsPrivateStreamVideoRelativePath(std::string_view path) {
  constexpr std::string_view prefix = "InternetBrowserVideos/stream-";
  if (!path.starts_with(prefix)) return false;
  path.remove_prefix(prefix.size());
  const auto slash = path.find('/');
  if (slash != 32) return false;
  for (char c : path.substr(0, slash))
    if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') ||
          (c >= 'a' && c <= 'f'))) return false;
  const auto filename = path.substr(slash + 1);
  return filename == "video.mp4" || filename == "audio.mp4";
}
// Relative to the original Flutter Videos directory; no nested/path traversal.
inline bool IsLegacyVideoRelativePath(std::string_view path) {
  return !path.empty() && path.find('/') == std::string_view::npos &&
      path.find('\\') == std::string_view::npos && IsVideoFileName(path);
}
}  // namespace internet_browser
#endif
