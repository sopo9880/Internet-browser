#include "chrome/browser/internet_browser/video_subtitles.h"

#include <string>
#include <string_view>
#include <vector>
#include "build/build_config.h"
#if BUILDFLAG(IS_POSIX)
#include <sys/stat.h>
#endif
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/i18n/icu_string_conversions.h"
#include "base/strings/string_util.h"
#include "base/strings/utf_string_conversions.h"
#include "net/base/filename_util.h"
#include "url/gurl.h"

namespace internet_browser {
namespace {
constexpr size_t kMaxSubtitleBytes = 2 * 1024 * 1024;
std::string Format(const base::FilePath& path) {
  auto extension = base::ToLowerASCII(path.FinalExtension());
  if (extension == FILE_PATH_LITERAL(".srt")) return "srt";
  if (extension == FILE_PATH_LITERAL(".vtt")) return "vtt";
  if (extension == FILE_PATH_LITERAL(".ass")) return "ass";
  return {};
}
std::string Decode(std::string bytes) {
  if (bytes.starts_with("\xef\xbb\xbf")) bytes.erase(0, 3);
  if (base::IsStringUTF8(bytes)) return bytes;
  const char* encoding = bytes.starts_with("\xff\xfe") ? "UTF-16LE" :
                         bytes.starts_with("\xfe\xff") ? "UTF-16BE" : "windows-949";
  if (std::string_view(encoding).starts_with("UTF-16")) bytes.erase(0, 2);
  std::u16string decoded;
  if (!base::CodepageToUTF16(bytes, encoding, base::OnStringConversionError::FAIL, &decoded))
    return {};
  return base::UTF16ToUTF8(decoded);
}
}  // namespace
base::DictValue LoadVideoSubtitles(base::DictValue options) {
  std::vector<base::FilePath> candidates;
  if (const auto* stored = options.FindString("subtitlePath"); stored && stored->size() <= 4096)
    candidates.push_back(base::FilePath::FromUTF8Unsafe(*stored));
  base::FilePath video;
  const auto* url = options.FindString("url");
  if (url && net::FileURLToFilePath(GURL(*url), &video) && !video.IsNetwork()) {
    for (const auto* extension : {FILE_PATH_LITERAL("srt"), FILE_PATH_LITERAL("vtt"), FILE_PATH_LITERAL("ass")})
      candidates.push_back(video.ReplaceExtension(extension));
  }
  for (const auto& path : candidates) {
    auto format = Format(path);
    base::File::Info info;
    // Reject UNC/device paths and special files before attempting a read.
    if (format.empty() || !path.IsAbsolute() || path.IsNetwork() ||
        !base::GetFileInfo(path, &info) || info.is_directory ||
        info.size <= 0 || info.size > static_cast<int64_t>(kMaxSubtitleBytes)) continue;
#if BUILDFLAG(IS_POSIX)
    struct stat details;
    if (stat(path.value().c_str(), &details) != 0 || !S_ISREG(details.st_mode)) continue;
#endif
    std::string bytes;
    if (!base::ReadFileToStringWithMaxSize(path, &bytes, kMaxSubtitleBytes)) continue;
    auto text = Decode(std::move(bytes));
    if (text.empty() || text.size() > kMaxSubtitleBytes || text.find('\0') != std::string::npos) continue;
    base::DictValue subtitle;
    subtitle.Set("format", format);
    subtitle.Set("text", text);
    subtitle.Set("label", path.BaseName().AsUTF8Unsafe());
    options.Set("subtitle", std::move(subtitle));
    break;
  }
  options.Remove("subtitlePath");
  return options;
}
}  // namespace internet_browser
