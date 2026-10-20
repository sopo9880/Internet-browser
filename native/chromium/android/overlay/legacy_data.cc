#include "chrome/browser/internet_browser/legacy_data.h"

#include <set>
#include <string>

#include "base/android/path_utils.h"
#include "base/files/file_enumerator.h"
#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "net/base/filename_util.h"
#include "url/gurl.h"

namespace internet_browser {
namespace {
base::DictValue ReadDictionary(const base::FilePath& path) {
  std::string data;
  if (!base::ReadFileToStringWithMaxSize(path, &data, 4 * 1024 * 1024))
    return {};
  auto value = base::JSONReader::ReadDict(data, base::JSON_PARSE_RFC);
  return value ? std::move(*value) : base::DictValue();
}

base::ListValue LegacyUrls(const base::DictValue& data, const std::string& key) {
  base::ListValue result;
  std::set<std::string> seen;
  if (const auto* list = data.FindList(key)) {
    for (const auto& value : *list) {
      if (!value.is_string())
        continue;
      GURL url(value.GetString());
      if (url.is_valid() && url.SchemeIsHTTPOrHTTPS() && seen.insert(url.spec()).second)
        result.Append(url.spec());
    }
  }
  return result;
}
}  // namespace

base::DictValue ReadLegacyData() {
  base::DictValue result;
  base::FilePath data;
  if (!base::android::GetDataDirectory(&data))
    return result;
  auto normalized = ReadDictionary(data.AppendASCII("internet-browser-legacy.json"));
  result.Set("found", normalized.FindBool("found").value_or(false));
  result.Set("bookmarks", LegacyUrls(normalized, "bookmarks"));
  result.Set("history", LegacyUrls(normalized, "history"));
  if (const auto* settings = normalized.FindDict("settings"))
    result.Set("settings", settings->Clone());
  return result;
}

base::DictValue ReadVideoLibrary() {
  base::DictValue result;
  base::ListValue videos;
  base::FilePath data;
  if (!base::android::GetDataDirectory(&data)) {
    result.Set("videos", std::move(videos));
    return result;
  }
  // Flutter's Android documents directory is app_flutter, beside app_chrome.
  // Retain its original files and metadata; never move or overwrite videos.
  auto directory = data.DirName().AppendASCII("app_flutter").AppendASCII("Videos");
  auto metadata = ReadDictionary(directory.AppendASCII("library.json"));
  const auto* entries = metadata.FindDict("items");
  base::FileEnumerator files(directory, false, base::FileEnumerator::FILES);
  for (auto path = files.Next(); !path.empty(); path = files.Next()) {
    if (base::IsLink(path) ||
        !(path.MatchesExtension(FILE_PATH_LITERAL(".mp4")) ||
          path.MatchesExtension(FILE_PATH_LITERAL(".webm")) ||
          path.MatchesExtension(FILE_PATH_LITERAL(".mkv")) ||
          path.MatchesExtension(FILE_PATH_LITERAL(".mov"))))
      continue;
    std::string name = path.BaseName().AsUTF8Unsafe();
    base::DictValue item;
    item.Set("title", name);
    item.Set("url", net::FilePathToFileURL(path).spec());
    if (entries) {
      if (const auto* entry = entries->FindDict(name)) {
        if (const auto* title = entry->FindString("title"))
          item.Set("title", *title);
      }
    }
    videos.Append(std::move(item));
  }
  result.Set("videos", std::move(videos));
  return result;
}
}  // namespace internet_browser
