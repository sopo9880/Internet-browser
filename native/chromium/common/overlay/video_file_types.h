#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_FILE_TYPES_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_FILE_TYPES_H_
#include <string>
#include <string_view>
namespace internet_browser {
inline bool IsVideoFileName(std::string_view name) {
  const auto dot = name.find_last_of('.');
  if (dot == std::string_view::npos) return false;
  std::string extension(name.substr(dot));
  for (auto& character : extension)
    if (character >= 'A' && character <= 'Z') character += 'a' - 'A';
  for (const auto* allowed : {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi", ".3gp", ".m2ts", ".ts", ".flv"})
    if (extension == allowed) return true;
  return false;
}
}  // namespace internet_browser
#endif
