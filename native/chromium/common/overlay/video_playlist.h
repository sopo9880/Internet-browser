#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PLAYLIST_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PLAYLIST_H_
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace internet_browser {
struct VideoPlaylistPart {
  std::string address;
  std::string quality;
};
struct VideoPlaylist {
  std::vector<VideoPlaylistPart> variants;
  std::vector<VideoPlaylistPart> parts;
  std::string extension = ".ts";
  std::string error;
};
inline std::string PlaylistTrim(std::string value) {
  const auto first = value.find_first_not_of(" \r\n\t");
  if (first == std::string::npos) return {};
  return value.substr(first, value.find_last_not_of(" \r\n\t") - first + 1);
}
inline std::map<std::string, std::string> PlaylistAttributes(const std::string& text) {
  std::map<std::string, std::string> result;
  size_t start = 0;
  while (start < text.size()) {
    const auto equals = text.find('=', start);
    if (equals == std::string::npos) break;
    const auto key = PlaylistTrim(text.substr(start, equals - start));
    start = equals + 1;
    std::string value;
    if (start < text.size() && text[start] == '"') {
      const auto end = text.find('"', ++start);
      if (end == std::string::npos) break;
      value = text.substr(start, end - start); start = end + 1;
      if (start < text.size() && text[start] != ',') break;
    } else {
      const auto end = text.find(',', start);
      value = PlaylistTrim(text.substr(start, end - start));
      start = end == std::string::npos ? text.size() : end;
    }
    result[key] = value;
    if (start < text.size() && text[start] == ',') ++start;
  }
  return result;
}
// Deliberately bounded VOD support. Never save encrypted/live/multi-track
// playlists as if they were complete playable files.
inline VideoPlaylist ParseVideoPlaylist(const std::string& text) {
  VideoPlaylist result;
  if (text.size() > 2 * 1024 * 1024 || !text.starts_with("#EXTM3U")) {
    result.error = "올바른 HLS 재생 목록이 아닙니다."; return result;
  }
  bool ended = false, expect_variant = false;
  std::string quality;
  for (size_t start = 0; start < text.size();) {
    const auto end = text.find('\n', start);
    const auto line = PlaylistTrim(text.substr(start, end - start));
    start = end == std::string::npos ? text.size() : end + 1;
    if (line.empty()) continue;
    if (line.starts_with("#EXT-X-KEY:") || line.starts_with("#EXT-X-SESSION-KEY:")) {
      const auto attrs = PlaylistAttributes(line.substr(line.find(':') + 1));
      const auto method = attrs.find("METHOD");
      if (method == attrs.end() || method->second != "NONE") {
        result.error = "암호화되거나 보호된 HLS 영상은 저장할 수 없습니다."; return result;
      }
    } else if (line.starts_with("#EXT-X-MEDIA:")) {
      const auto attrs = PlaylistAttributes(line.substr(13));
      const auto type = attrs.find("TYPE");
      if (type != attrs.end() && type->second == "AUDIO" && attrs.contains("URI")) {
        result.error = "별도의 음성 트랙이 있는 HLS 영상은 합치기 지원이 필요합니다."; return result;
      }
    } else if (line.starts_with("#EXT-X-STREAM-INF:")) {
      auto attrs = PlaylistAttributes(line.substr(18));
      quality = attrs["RESOLUTION"];
      if (quality.empty()) quality = attrs["BANDWIDTH"].empty() ? "원본" : attrs["BANDWIDTH"] + " bps";
      expect_variant = true;
    } else if (line.starts_with("#EXT-X-MAP:")) {
      const auto attrs = PlaylistAttributes(line.substr(11));
      if (!attrs.contains("URI") || attrs.contains("BYTERANGE") || !result.parts.empty()) {
        result.error = "이 HLS 초기화 구간은 지원하지 않습니다."; return result;
      }
      result.parts.push_back({attrs.at("URI"), {}}); result.extension = ".mp4";
    } else if (line.starts_with("#EXT-X-BYTERANGE:") || line.starts_with("#EXT-X-DISCONTINUITY") ||
               line.starts_with("#EXT-X-I-FRAMES-ONLY") || line.starts_with("#EXT-X-GAP")) {
      result.error = "구간 전환·바이트 범위가 있는 HLS 영상은 현재 지원하지 않습니다."; return result;
    } else if (line == "#EXT-X-ENDLIST") ended = true;
    else if (line.front() != '#') {
      if (line.size() > 16384) { result.error = "영상 구간 주소가 너무 깁니다."; return result; }
      if (expect_variant) { result.variants.push_back({line, quality}); expect_variant = false; }
      else result.parts.push_back({line, {}});
    }
    if (result.parts.size() > 20000 || result.variants.size() > 60) {
      result.error = "영상의 구간 수가 지원 범위를 초과합니다."; return result;
    }
  }
  if (expect_variant || (!result.variants.empty() && !result.parts.empty()) ||
      (result.variants.empty() && (result.parts.empty() || !ended)))
    result.error = "진행 중인 생방송 또는 불완전한 HLS 영상은 저장할 수 없습니다.";
  return result;
}
}
#endif
