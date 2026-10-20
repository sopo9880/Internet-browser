#include "chrome/browser/internet_browser/legacy_data.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/browser/internet_browser/video_file_types.h"
#include "chrome/browser/internet_browser/legacy_test_paths.h"

#include <set>
#include <string>

#include "base/base_paths_win.h"
#include "base/files/file_enumerator.h"
#include "base/files/file_util.h"
#include "base/json/json_reader.h"
#include "base/path_service.h"
#include "base/strings/utf_string_conversions.h"
#include "chrome/common/chrome_paths_internal.h"
#include "net/base/filename_util.h"
#include "url/gurl.h"

namespace internet_browser {
namespace {
base::DictValue ReadDictionary(const base::FilePath& path) {
  std::string data;
  if (!base::ReadFileToStringWithMaxSize(path, &data, 4 * 1024 * 1024))
    return {};
  auto result = base::JSONReader::ReadDict(data, base::JSON_PARSE_RFC);
  return result ? std::move(*result) : base::DictValue();
}

base::ListValue LegacyUrls(const base::DictValue& data, const std::string& key) {
  const auto* values = data.FindList("flutter." + key);
  if (!values)
    values = data.FindList(key);
  base::ListValue result;
  std::set<std::string> seen;
  if (values) {
    for (const auto& value : *values) {
      if (!value.is_string())
        continue;
      GURL url(value.GetString());
      if (url.is_valid() && url.SchemeIsHTTPOrHTTPS() &&
          seen.insert(url.spec()).second)
        result.Append(url.spec());
    }
  }
  return result;
}
}  // namespace

base::DictValue ReadLegacyData() {
  base::DictValue result;
  base::FilePath roaming;
  base::FilePath fallback;
  if (base::PathService::Get(base::DIR_ROAMING_APP_DATA, &roaming))
    fallback = roaming.AppendASCII("io.github.sopo9880").AppendASCII("internet_browser");
  const auto directory = NativeFixtureDirectory("internet-browser-test-legacy-directory", fallback);
  if (directory.empty()) return result;
  const auto file = directory.AppendASCII("shared_preferences.json");
  auto preferences = ReadDictionary(file);
  result.Set("found", !preferences.empty());
  result.Set("bookmarks", LegacyUrls(preferences, "bookmarks"));
  // Legacy history contains URLs but no visit timestamps. Keep it accessible
  // without creating invented visits in Chromium's history database.
  result.Set("history", LegacyUrls(preferences, "history"));
  base::DictValue settings;
  for (const char* name : {"dpi_enabled", "dpi_options_preset", "dpi_options_split",
       "dpi_options_split_value", "dpi_options_disorder", "dpi_options_disorder_value",
       "dpi_options_tls", "dpi_options_tls_value", "dpi_options_auto", "dpi_options_http",
       "dpi_options_fake", "dpi_options_ttl", "update_auto_check",
       "update_last_auto_check", "update_snoozed_tag", "update_snoozed_until"}) {
    const auto* value = preferences.Find(std::string("flutter.") + name);
    if (!value)
      value = preferences.Find(name);
    if (value)
      settings.Set(name, value->Clone());
  }
  result.Set("settings", std::move(settings));
  return result;
}

base::DictValue ReadVideoLibrary(const base::FilePath& state_file) {
  base::DictValue result;
  base::ListValue videos;
  base::FilePath documents;
  base::FilePath fallback;
  if (chrome::GetUserDocumentsDirectory(&documents)) fallback = documents.AppendASCII("Videos");
  const auto directory = NativeFixtureDirectory("internet-browser-test-library", fallback);
  if (directory.empty()) {
    result.Set("videos", std::move(videos));
    return result;
  }
  auto metadata = ReadDictionary(directory.AppendASCII("library.json"));
  auto native = ReadVideoState(state_file);
  const auto* entries = metadata.FindDict("items");
  base::FileEnumerator files(directory, false, base::FileEnumerator::FILES);
  for (auto path = files.Next(); !path.empty(); path = files.Next()) {
    if (base::IsLink(path) || !IsVideoFileName(path.BaseName().AsUTF8Unsafe()))
      continue;
    base::DictValue item;
    std::string name = path.BaseName().AsUTF8Unsafe();
    item.Set("title", path.BaseName().RemoveExtension().AsUTF8Unsafe());
    item.Set("url", net::FilePathToFileURL(path).spec());
    AddVideoMetadata(item, name, entries ? entries->FindDict(name) : nullptr, native);
    videos.Append(std::move(item));
  }
  result.Set("videos", std::move(videos));
  return result;
}
}  // namespace internet_browser
