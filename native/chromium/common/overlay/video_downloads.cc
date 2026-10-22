#include "chrome/browser/internet_browser/video_downloads.h"
#include <algorithm>
#include <set>
#include <utility>
#include "base/files/file_util.h"
#include "base/files/file_enumerator.h"
#include "base/json/json_reader.h"
#include "base/strings/utf_string_conversions.h"
#include "build/build_config.h"
#include "chrome/browser/internet_browser/legacy_data.h"
#include "chrome/browser/internet_browser/video_file_types.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "components/download/public/common/download_item.h"
#include "content/public/browser/browser_context.h"
#include "content/public/browser/download_item_utils.h"
#include "content/public/browser/download_manager.h"
#include "content/public/browser/web_contents.h"
#include "net/base/filename_util.h"
#include "url/gurl.h"

namespace internet_browser {
std::vector<CompletedVideoDownload> CollectVideoDownloads(content::BrowserContext* context) {
  std::vector<CompletedVideoDownload> result;
  auto* manager = context->GetDownloadManager();
  if (!manager) return result;
  content::DownloadManager::DownloadVector items;
  manager->GetAllDownloads(&items);
  std::sort(items.begin(), items.end(), [](const auto& left, const auto& right) {
    if (left->GetEndTime() != right->GetEndTime()) return left->GetEndTime() > right->GetEndTime();
    return left->GetGuid() < right->GetGuid();
  });
  for (const auto& pointer : items) {
    const auto* item = pointer.get();
    const auto name = item->GetFileNameToReportUser();
    if (item->GetState() != download::DownloadItem::COMPLETE || item->GetFileExternallyRemoved() ||
        item->IsDangerous() || item->IsInsecure() || !IsVideoFileName(name.AsUTF8Unsafe()))
      continue;
    CompletedVideoDownload video;
    video.path = item->GetTargetFilePath();
    video.key = "download:" + item->GetGuid();
    video.title = name.BaseName().RemoveExtension().AsUTF8Unsafe();
    if (auto* contents = content::DownloadItemUtils::GetWebContents(item);
        contents && contents->GetLastCommittedURL() == item->GetTabUrl() && item->GetTabUrl().SchemeIsHTTPOrHTTPS()) {
      const auto page_title = NormalizeVideoTitle(base::UTF16ToUTF8(contents->GetTitle()));
      if (!page_title.empty()) video.title = page_title;
    }
    if (item->GetTabUrl().SchemeIsHTTPOrHTTPS()) video.page = item->GetTabUrl().spec();
    else if (item->GetReferrerUrl().SchemeIsHTTPOrHTTPS()) video.page = item->GetReferrerUrl().spec();
    result.push_back(std::move(video));
  }
  return result;
}

base::DictValue ReadVideoLibraryWithDownloads(const base::FilePath& state,
                                             std::vector<CompletedVideoDownload> downloads, bool private_session) {
  if (!private_session && !state.empty()) {
    const auto parent = state.DirName().AppendASCII("InternetBrowserVideos");
    if (!base::IsLink(parent)) {
      base::FileEnumerator folders(parent, false, base::FileEnumerator::DIRECTORIES);
      for (auto directory = folders.Next(); !directory.empty(); directory = folders.Next()) {
        if (base::IsLink(directory)) continue;
        std::string text;
        if (!base::ReadFileToStringWithMaxSize(directory.AppendASCII("complete.json"), &text, 8192)) continue;
        const auto metadata = base::JSONReader::ReadDict(text, base::JSON_PARSE_RFC);
        const auto* title = metadata ? metadata->FindString("title") : nullptr;
        if (!title) continue;
        CompletedVideoDownload video;
        video.path = directory.AppendASCII("video.mp4");
        if (const auto* media = metadata->FindString("mediaFile")) {
          if (*media != "video.mp4" && *media != "video.webm" &&
              *media != "video.avi" && *media != "video.flv") continue;
          video.path = directory.AppendASCII(*media);
        }
        if (metadata->FindBool("separateAudio").value_or(false)) {
          video.audio_path = directory.AppendASCII("audio.mp4");
          base::File::Info info;
          if (base::IsLink(video.audio_path) || !base::GetFileInfo(video.audio_path, &info) || info.is_directory) continue;
        }
        video.key = "stream:" + directory.BaseName().AsUTF8Unsafe();
        video.title = NormalizeVideoTitle(*title);
        if (const auto* page = metadata->FindString("sourcePage"); page && GURL(*page).SchemeIsHTTPOrHTTPS()) video.page = *page;
        downloads.push_back(std::move(video));
        if (downloads.size() >= 10000) break;
      }
    }
  }
  auto library = ReadVideoLibrary(state);
  library.Set("privateSession", private_session);
  auto* videos = library.FindList("videos");
  if (!videos) return library;
  std::set<std::string> seen;
  for (const auto& value : *videos)
    if (const auto* url = value.GetDict().FindString("url")) seen.insert(*url);
  base::DictValue defaults;
  base::ListValue additions;
  for (const auto& download : downloads) {
    GURL url;
#if BUILDFLAG(IS_ANDROID)
    if (download.path.IsContentUri() || download.path.IsVirtualDocumentPath()) {
      const auto content = base::ResolveToContentUri(download.path);
      if (!content || !base::PathExists(*content)) continue;
      url = GURL(content->value());
    } else
#endif
    {
      base::File::Info info;
      if (!download.path.IsAbsolute() || base::IsLink(download.path) ||
          !base::GetFileInfo(download.path, &info) || info.is_directory)
        continue;
      url = net::FilePathToFileURL(download.path);
    }
    if (!url.is_valid() || !seen.insert(url.spec()).second) continue;
    base::DictValue item;
    item.Set("url", url.spec());
    item.Set("name", download.key);
    item.Set("title", download.title);
    item.Set("sourcePage", download.page);
    if (!download.audio_path.empty()) item.Set("audioUrl", net::FilePathToFileURL(download.audio_path).spec());
    base::DictValue metadata;
    metadata.Set("title", download.title);
    metadata.Set("sourcePage", download.page);
    defaults.Set(download.key, std::move(metadata));
    additions.Append(std::move(item));
  }
  auto native = private_session ? ReadVideoState(state) : MergeVideoCatalog(state, defaults);
  for (auto& value : additions) {
    auto& item = value.GetDict();
    const std::string key = *item.FindString("name");
    AddVideoMetadata(item, key, nullptr, native);
  }
  // New downloads are already ordered newest first; retain every legacy row.
  for (auto& value : *videos) additions.Append(std::move(value));
  additions.EraseIf([&](const auto& value) {
    const auto* key = value.GetDict().FindString("name");
    const auto* saved = key ? native.FindDict(*key) : nullptr;
    return saved && saved->FindBool("hidden").value_or(false);
  });
  for (auto& value : additions) {
    auto& row = value.GetDict();
    const auto* url = row.FindString("url");
    base::FilePath path;
    if (url && net::FileURLToFilePath(GURL(*url), &path)) {
      double size = static_cast<double>(base::GetFileSize(path).value_or(0));
      if (const auto* audio = row.FindString("audioUrl"); audio && net::FileURLToFilePath(GURL(*audio), &path))
        size += static_cast<double>(base::GetFileSize(path).value_or(0));
      row.Set("sizeBytes", size);
    }
  }
  library.Set("videos", std::move(additions));
  return library;
}
base::DictValue DeleteLibraryVideo(const base::FilePath& state,
                                  std::vector<CompletedVideoDownload> downloads,
                                  const std::string& requested, bool delete_file) {
  base::DictValue result;
  // Resolve only an item from the current profile's completed library. Never
  // accept a renderer-provided filesystem path or recursively remove a folder.
  auto library = ReadVideoLibraryWithDownloads(state, downloads);
  const auto* rows = library.FindList("videos");
  if (!rows) return result;
  for (const auto& value : *rows) {
    const auto& row = value.GetDict();
    const auto* url = row.FindString("url");
    const auto* key = row.FindString("name");
    if (!url || !key || *url != requested) continue;
    if (delete_file) {
      base::FilePath file;
      for (const auto& download : downloads)
        if (download.key == *key) { file = download.path; break; }
      if (file.empty() && !net::FileURLToFilePath(GURL(*url), &file)) {
        result.Set("error", "파일 위치를 확인하지 못했습니다."); return result;
      }
      if (base::IsLink(file) || base::IsLink(file.DirName())) {
        result.Set("error", "연결된 파일은 삭제하지 않습니다."); return result;
      }
      if (key->starts_with("stream:")) {
        const auto parent = state.DirName().AppendASCII("InternetBrowserVideos");
        if (file.DirName().DirName() != parent || base::IsLink(parent) ||
            (file.BaseName().AsUTF8Unsafe() != "video.mp4" &&
             file.BaseName().AsUTF8Unsafe() != "video.webm" &&
             file.BaseName().AsUTF8Unsafe() != "video.avi" &&
             file.BaseName().AsUTF8Unsafe() != "video.flv") ||
            *key != "stream:" + file.DirName().BaseName().AsUTF8Unsafe()) return result;
        for (const char* name : {"video.mp4", "video.webm", "video.avi", "video.flv", "audio.mp4", "complete.json"}) {
          const auto target = file.DirName().AppendASCII(name);
          if (base::IsLink(target)) { result.Set("error", "연결된 파일은 삭제하지 않습니다."); return result; }
        }
        for (const char* name : {"video.mp4", "video.webm", "video.avi", "video.flv", "audio.mp4", "complete.json"}) {
          const auto target = file.DirName().AppendASCII(name);
          if (base::PathExists(target) && !base::DeleteFile(target)) {
            result.Set("error", "일부 파일을 삭제하지 못했습니다. 재생을 종료한 뒤 다시 시도해 주세요."); return result;
          }
        }
        base::DeleteFile(file.DirName());  // Empty directory only.
      } else if (!base::DeleteFile(file)) {
        result.Set("error", "파일을 삭제하지 못했습니다. 재생 또는 파일 권한을 확인해 주세요."); return result;
      }
    }
    base::AutoLock lock(VideoStateLock());
    auto catalog = ReadVideoState(state);
    auto* entry = catalog.FindDict(*key);
    auto saved = entry ? entry->Clone() : base::DictValue();
    saved.Set("hidden", true); catalog.Set(*key, std::move(saved));
    std::string serialized;
    const bool stored = !state.empty() && base::JSONWriter::Write(catalog, &serialized) &&
        serialized.size() <= 4 * 1024 * 1024 && base::ImportantFileWriter::WriteFileAtomically(state, serialized);
    result.Set("deleted", stored); result.Set("fileDeleted", delete_file);
    if (!stored) result.Set("error", "목록 변경을 저장하지 못했습니다.");
    return result;
  }
  result.Set("error", "영상을 찾지 못했습니다. 목록을 새로고침해 주세요.");
  return result;
}
}  // namespace internet_browser
