#include <cassert>
#include <iostream>
#include "native/chromium/common/overlay/video_file_types.h"
int main() {
  using internet_browser::IsVideoFileName;
  // The saved-library extensions accepted by the existing Dart VideoDetector.
  for (const auto* filename : {"recording.MP4", "clip.webm", "camera.MOV", "show.m4v", "movie.mkv",
                               "archive.AVI", "phone.3gp", "disc.m2ts", "stream.TS", "older.flv"})
    assert(IsVideoFileName(filename));
  for (const auto* filename : {"", "document.pdf", "movie.mp4.exe", "movie.webm.part", "video.mp4?name=other", "movie.mp40"})
    assert(!IsVideoFileName(filename));
  std::cout << "Legacy video-library filename checks passed; codec support is a separate runtime check.\n";
}
