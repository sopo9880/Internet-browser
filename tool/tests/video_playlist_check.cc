#include <cassert>
#include "native/chromium/common/overlay/video_playlist.h"
int main() {
  using internet_browser::ParseVideoPlaylist;
  auto vod = ParseVideoPlaylist("#EXTM3U\n#EXTINF:2,\na.ts\n#EXTINF:2,\nb.ts\n#EXT-X-ENDLIST\n");
  assert(vod.error.empty() && vod.parts.size() == 2 && vod.extension == ".ts");
  auto master = ParseVideoPlaylist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000,CODECS=\"avc1,mp4a\",RESOLUTION=1280x720\n720/main.m3u8\n");
  assert(master.error.empty() && master.variants.size() == 1 && master.variants[0].quality == "1280x720");
  assert(master.variants[0].bandwidth == "900000");
  auto average = ParseVideoPlaylist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=900000,AVERAGE-BANDWIDTH=500000\nv.m3u8\n");
  assert(average.error.empty() && average.variants[0].bandwidth == "500000");
  auto mp4 = ParseVideoPlaylist("#EXTM3U\n#EXT-X-MAP:URI=\"init.mp4\"\n#EXTINF:3,\na.m4s\n#EXT-X-ENDLIST");
  assert(mp4.error.empty() && mp4.extension == ".mp4" && mp4.parts[0].address == "init.mp4");
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"key\"\na.ts\n#EXT-X-ENDLIST").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXTINF:3,\na.ts").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",URI=\"audio.m3u8\"\n#EXT-X-STREAM-INF:BANDWIDTH=100\nv.m3u8").error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-MAP:URI=\"init\",BYTERANGE=\"12@0\"\na\n#EXT-X-ENDLIST").error.empty());
  assert(!ParseVideoPlaylist("<html>denied</html>").error.empty());
  const std::string paired = "#EXTM3U\n"
      "#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",LANGUAGE=\"en\",URI=\"dub.m3u8\"\n"
      "#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",LANGUAGE=\"ko\",DEFAULT=YES,URI=\"original.m3u8\"\n"
      "#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080,FRAME-RATE=60.000,CODECS=\"avc1.64002a,mp4a.40.2\",AUDIO=\"a\"\n"
      "video.m3u8\n";
  assert(!ParseVideoPlaylist(paired).error.empty());  // Ordinary HLS path still refuses unsupported pairs.
  auto resolved = ParseVideoPlaylist(paired, true);
  assert(resolved.error.empty() && resolved.variants.size() == 1);
  assert(resolved.variants[0].audio_address == "original.m3u8");
  assert(resolved.variants[0].audio_language == "ko" && resolved.variants[0].frame_rate == "60.000");
  auto inband = ParseVideoPlaylist("#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID=\"a\",NAME=\"Original\"\n#EXT-X-STREAM-INF:AUDIO=\"a\",BANDWIDTH=500\nv.m3u8\n", true);
  assert(inband.error.empty() && inband.variants[0].audio_address.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-STREAM-INF:AUDIO=\"missing\"\nv.m3u8\n", true).error.empty());
  assert(!ParseVideoPlaylist("#EXTM3U\n#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI=\"secret\"\n", true).error.empty());
}
