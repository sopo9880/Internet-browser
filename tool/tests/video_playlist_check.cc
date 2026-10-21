#include <cassert>
#include "native/chromium/common/overlay/video_playlist.h"
int main() {
  using internet_browser::ParseVideoPlaylist;
  auto vod = ParseVideoPlaylist("#EXTM3U\n#EXTINF:2,\na.ts\n#EXTINF:2,\nb.ts\n#EXT-X-ENDLIST\n");
  assert(vod.error.empty() && vod.parts.size() == 2 && vod.extension == ".ts");
  auto master = ParseVideoPlaylist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000,CODECS=\"avc1,mp4a\",RESOLUTION=1280x720\n720/main.m3u8\n");
  assert(master.error.empty() && master.variants.size() == 1 && master.variants[0].quality == "1280x720");
  auto mp4 = ParseVideoPlaylist("#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:3,\na.m4s\n#EXT-X-ENDLIST");
  assert(mp4.error.empty() && mp4.extension == ".mp4" && mp4.parts[0].address == "init.mp4");
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"key\"\na.ts\n#EXT-X-ENDLIST").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXTINF:3,\na.ts").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",URI=\"audio.m3u8\"\n#EXT-X-STREAM-INF:BANDWIDTH=100\nv.m3u8").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-MAP:URI=\"init\",BYTERANGE=\"12@0\"\na\n#EXT-X-ENDLIST").error.empty());
  assert(!ParseVideoPlaylist("<html>denied</html>").error.empty());
}
