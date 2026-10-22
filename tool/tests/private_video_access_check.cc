#include <cassert>
#include <string>
#include "native/chromium/android/overlay/private_video_access.h"

int main() {
  using internet_browser::IsPrivateStreamVideoRelativePath;
  using internet_browser::IsLegacyVideoRelativePath;
  const std::string job = "InternetBrowserVideos/stream-57C36868F2CC00D713B2481295A37BEE/";
  assert(IsPrivateStreamVideoRelativePath(job + "video.mp4"));
  assert(IsPrivateStreamVideoRelativePath(job + "audio.mp4"));
  for (const auto* filename : {"video.webm", "video.mkv", "video.avi", "video.flv"})
    assert(IsPrivateStreamVideoRelativePath(job + filename));
  for (const auto* filename : {"complete.json", "../Cookies", "../../Login Data",
                             "nested/video.mp4", "video.mp4/other", "other.mp4"})
    assert(!IsPrivateStreamVideoRelativePath(job + filename));
  for (const auto* path : {"InternetBrowserVideos/stream-short/video.mp4",
       "InternetBrowserVideos/stream-57C36868F2CC00D713B2481295A37BEZ/video.mp4",
       "../InternetBrowserVideos/stream-57C36868F2CC00D713B2481295A37BEE/video.mp4",
       "/data/user/0/other.profile/video.mp4", "Cookies", "Login Data"})
    assert(!IsPrivateStreamVideoRelativePath(path));
  assert(IsLegacyVideoRelativePath("saved.MP4"));
  assert(IsLegacyVideoRelativePath("saved.webm"));
  for (const auto* path : {"library.json", "../secret.mp4", "subdir/file.mp4",
                          "..\\secret.mp4", "Cookies", ""})
    assert(!IsLegacyVideoRelativePath(path));
}
