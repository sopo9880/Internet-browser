#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_DOWNLOADS_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_DOWNLOADS_H_
#include <string>
#include <vector>
#include "base/files/file_path.h"
#include "base/values.h"
namespace content { class BrowserContext; }
namespace internet_browser {
struct CompletedVideoDownload {
  base::FilePath path;
  std::string key;
  std::string title;
  std::string page;
};
// UI thread only: copy values, never pass live DownloadItems to a worker.
std::vector<CompletedVideoDownload> CollectVideoDownloads(content::BrowserContext* context);
// Worker only: merge this profile's completed downloads with the legacy library.
base::DictValue ReadVideoLibraryWithDownloads(const base::FilePath& state,
                                             std::vector<CompletedVideoDownload> downloads,
                                             bool private_session = false);
}
#endif
