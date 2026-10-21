#include "chrome/browser/internet_browser/video_dash.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>
#include "base/strings/string_number_conversions.h"
#include "chrome/browser/internet_browser/video_playlist.h"
#include "services/data_decoder/public/cpp/safe_xml_parser.h"

namespace internet_browser {
namespace {
using Node = base::Value;
std::string Tag(const Node& node) {
  std::string name;
  data_decoder::GetXmlElementTagName(node, &name);
  const auto colon = name.find(':');
  return colon == std::string::npos ? name : name.substr(colon + 1);
}
std::vector<const Node*> Children(const Node& node, const char* tag) {
  std::vector<const Node*> result;
  if (const auto* list = data_decoder::GetXmlElementChildren(node))
    for (const auto& child : *list) if (Tag(child) == tag) result.push_back(&child);
  return result;
}
const Node* Child(const Node& node, const char* tag) {
  const auto list = Children(node, tag); return list.empty() ? nullptr : list.front();
}
std::string Attr(const Node& node, const char* name) { return data_decoder::GetXmlElementAttribute(node, name); }
std::string Text(const Node& node) {
  std::string text;
  data_decoder::GetXmlElementText(node, &text);
  return PlaylistTrim(text);
}
bool SafeUrl(const GURL& url) { return url.is_valid() && url.SchemeIsHTTPOrHTTPS() && !url.has_username() && !url.has_password() && url.spec().size() <= 16384; }
bool SafeTree(const Node& node, size_t& count, size_t depth = 0) {
  if (++count > 30000 || depth > 24 || Tag(node) == "ContentProtection" || Tag(node) == "Location") return false;
  if (const auto* children = data_decoder::GetXmlElementChildren(node))
    for (const auto& child : *children) if (!SafeTree(child, count, depth + 1)) return false;
  return true;
}
uint64_t Number(const std::string& text, uint64_t fallback = 0) {
  uint64_t value; return text.empty() ? fallback : base::StringToUint64(text, &value) ? value : 0;
}
double Duration(const std::string& text) {
  if (!text.starts_with("PT")) return 0;
  double result = 0; size_t start = 2;
  for (size_t i = 2; i < text.size(); ++i) {
    if (text[i] != 'H' && text[i] != 'M' && text[i] != 'S') continue;
    double value;
    if (!base::StringToDouble(text.substr(start, i - start), &value) || !std::isfinite(value) || value < 0) return 0;
    result += value * (text[i] == 'H' ? 3600 : text[i] == 'M' ? 60 : 1); start = i + 1;
  }
  return start == text.size() && result <= 43200 ? result : 0;
}
std::string Expand(const std::string& pattern, const std::string& id, uint64_t bandwidth, uint64_t number, uint64_t time) {
  std::string result;
  for (size_t i = 0; i < pattern.size();) {
    if (result.size() > 16384) return {};
    if (pattern[i] != '$') { result += pattern[i++]; continue; }
    if (i + 1 < pattern.size() && pattern[i + 1] == '$') { result += '$'; i += 2; continue; }
    const auto end = pattern.find('$', i + 1); if (end == std::string::npos) return {};
    auto key = pattern.substr(i + 1, end - i - 1); i = end + 1;
    uint64_t width = 0;
    const auto percent = key.find('%');
    if (percent != std::string::npos) {
      const auto format = key.substr(percent);
      if (!format.starts_with("%0") || !format.ends_with('d')) return {};
      width = Number(format.substr(2, format.size() - 3));
      if (width == 0 || width > 12) return {};
      key.resize(percent);
    }
    std::string value;
    if (key == "RepresentationID" && !width) value = id;
    else if (key == "Bandwidth") value = std::to_string(bandwidth);
    else if (key == "Number") value = std::to_string(number);
    else if (key == "Time") value = std::to_string(time);
    else return {};
    if (value.size() < width) value.insert(0, width - value.size(), '0');
    result += value;
  }
  return result;
}
struct Track {
  base::ListValue urls;
  std::string quality, language;
  uint64_t bandwidth = 0;
};
bool AddUrl(Track& track, GURL base, const std::string& address, size_t& bytes) {
  const auto url = base.Resolve(address);
  if (address.empty() || !SafeUrl(url) || track.urls.size() >= 20001 || (bytes += url.spec().size()) > 8 * 1024 * 1024) return false;
  track.urls.Append(url.spec()); return true;
}
bool BuildTrack(const std::vector<const Node*>& chain, GURL base, double duration, Track& output) {
  const Node* list = nullptr;
  const Node* templ = nullptr;
  std::vector<const Node*> templates;
  std::string mime, id;
  bool specific_base = false;
  for (const auto* node : chain) {
    if (const auto* child = Child(*node, "BaseURL")) {
      const auto address = Text(*child); if (address.empty()) return false;
      base = base.Resolve(address); specific_base = true;
    }
    if (!SafeUrl(base)) return false;
    if (const auto* child = Child(*node, "SegmentList")) { list = child; templ = nullptr; templates.clear(); }
    if (const auto* child = Child(*node, "SegmentTemplate")) { templ = child; templates.push_back(child); list = nullptr; }
    if (!Attr(*node, "mimeType").empty()) mime = Attr(*node, "mimeType");
    if (!Attr(*node, "id").empty()) id = Attr(*node, "id");
    if (const auto height = Number(Attr(*node, "height")); height && height <= 16384) output.quality = std::to_string(height) + "p";
    if (!Attr(*node, "lang").empty()) {
      const auto language = Attr(*node, "lang");
      if (language.size() <= 35 && std::all_of(language.begin(), language.end(), [](unsigned char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '-'; })) output.language = language;
    }
    if (!Attr(*node, "bandwidth").empty()) output.bandwidth = Number(Attr(*node, "bandwidth"));
  }
  if (mime != "video/mp4" && mime != "audio/mp4") return false;
  size_t bytes = 0;
  if (list) {
    const auto* init = Child(*list, "Initialization");
    if (!init || !Attr(*init, "range").empty() || !AddUrl(output, base, Attr(*init, "sourceURL"), bytes)) return false;
    for (const auto* segment : Children(*list, "SegmentURL")) {
      if (!Attr(*segment, "mediaRange").empty() || !AddUrl(output, base, Attr(*segment, "media"), bytes)) return false;
    }
    return output.urls.size() > 1;
  }
  if (!templ) {
    // A single MP4 BaseURL already contains the initialization/index/media;
    // downloading it whole avoids inventing byte-range or index semantics.
    if (!specific_base || base.path().ends_with('/')) return false;
    return AddUrl(output, base, base.spec(), bytes);
  }
  const auto template_attr = [&](const char* name) {
    for (auto it = templates.rbegin(); it != templates.rend(); ++it) { auto value = Attr(**it, name); if (!value.empty()) return value; }
    return std::string();
  };
  const auto init = Expand(template_attr("initialization"), id, output.bandwidth, 0, 0);
  if (!AddUrl(output, base, init, bytes)) return false;
  const auto timescale = Number(template_attr("timescale"), 1);
  const auto offset = Number(template_attr("presentationTimeOffset"));
  auto number = Number(template_attr("startNumber"), 1);
  const auto pattern = template_attr("media");
  if (!timescale || timescale > 1000000000 || !number || pattern.empty()) return false;
  const auto limit = duration > 0 ? static_cast<uint64_t>(std::ceil(duration * timescale)) + offset : 0;
  const auto emit = [&](uint64_t time) {
    return AddUrl(output, base, Expand(pattern, id, output.bandwidth, number++, time), bytes);
  };
  const Node* timeline = nullptr;
  for (auto it = templates.rbegin(); it != templates.rend() && !timeline; ++it) timeline = Child(**it, "SegmentTimeline");
  if (timeline) {
    const auto nodes = Children(*timeline, "S"); uint64_t time = 0;
    for (size_t i = 0; i < nodes.size(); ++i) {
      const auto* node = nodes[i]; const auto ticks = Number(Attr(*node, "d"));
      if (!Attr(*node, "t").empty()) time = Number(Attr(*node, "t"));
      int64_t repeat = 0;
      if (!Attr(*node, "r").empty() && !base::StringToInt64(Attr(*node, "r"), &repeat)) return false;
      if (!ticks || ticks > 1000000000000ULL || repeat < -1 || repeat > 20000) return false;
      if (repeat == -1) {
        const auto end = i + 1 < nodes.size() ? Number(Attr(*nodes[i + 1], "t")) : limit;
        if (!end || end <= time) return false;
        repeat = static_cast<int64_t>((end - time - 1) / ticks);
      }
      for (int64_t n = 0; n <= repeat; ++n) {
        if (!emit(time) || time > std::numeric_limits<uint64_t>::max() - ticks) return false;
        time += ticks;
      }
    }
  } else {
    const auto ticks = Number(template_attr("duration"));
    if (!ticks || !limit || limit <= offset) return false;
    const auto count = (limit - offset - 1) / ticks + 1;
    if (count > 20000) return false;
    for (uint64_t i = 0; i < count; ++i) if (!emit(i * ticks)) return false;
  }
  return output.urls.size() > 1;
}
base::DictValue Error(const char* text) { base::DictValue result; result.Set("error", text); return result; }
}
base::DictValue ParseVideoDash(const base::Value& root, const GURL& manifest) {
  size_t count = 0;
  if (Tag(root) != "MPD" || !SafeTree(root, count)) return Error("보호되거나 지원 범위를 벗어난 DASH 재생 목록입니다.");
  if (!Attr(root, "type").empty() && Attr(root, "type") != "static") return Error("진행 중인 생방송 또는 알 수 없는 종류의 DASH 영상은 저장할 수 없습니다.");
  const auto periods = Children(root, "Period");
  if (periods.size() != 1) return Error("구간 전환이 있는 DASH 영상은 현재 지원하지 않습니다.");
  const auto* period = periods.front();
  const auto duration = Duration(Attr(*period, "duration").empty() ? Attr(root, "mediaPresentationDuration") : Attr(*period, "duration"));
  std::vector<Track> videos, audios;
  size_t plan_bytes = 0;
  bool audio_declared = false;
  for (const auto* adaptation : Children(*period, "AdaptationSet")) {
    auto type = Attr(*adaptation, "contentType");
    const auto mime = Attr(*adaptation, "mimeType");
    if (type.empty()) type = mime.starts_with("audio/") ? "audio" : mime.starts_with("video/") ? "video" : "";
    if (type == "audio") audio_declared = true;
    for (const auto* representation : Children(*adaptation, "Representation")) {
      const auto rep_mime = Attr(*representation, "mimeType");
      const auto actual_type = type.empty() ? rep_mime.starts_with("audio/") ? "audio" : rep_mime.starts_with("video/") ? "video" : "" : type;
      if (actual_type == "audio") audio_declared = true;
      if (actual_type != "audio" && actual_type != "video") continue;
      Track track;
      if (!BuildTrack({&root, period, adaptation, representation}, manifest, duration, track)) continue;
      for (const auto& address : track.urls) plan_bytes += address.GetString().size();
      if (plan_bytes > 16 * 1024 * 1024) return Error("DASH 구간 정보가 지원 크기를 초과했습니다.");
      if (actual_type == "audio") audios.push_back(std::move(track));
      else videos.push_back(std::move(track));
      if (videos.size() + audios.size() > 120) return Error("DASH 화질 항목이 너무 많습니다.");
    }
  }
  if (videos.empty() || (audio_declared && audios.empty())) return Error("저장 가능한 MP4 영상·음성 구간을 찾지 못했습니다. 바이트 범위·지원하지 않는 형식일 수 있습니다.");
  const Track* audio = audios.empty() ? nullptr : &*std::max_element(audios.begin(), audios.end(), [](const auto& a, const auto& b) { return a.bandwidth < b.bandwidth; });
  base::ListValue variants;
  size_t output_bytes = 0;
  for (auto& track : videos) {
    for (const auto& address : track.urls) output_bytes += address.GetString().size();
    if (audio) for (const auto& address : audio->urls) output_bytes += address.GetString().size();
    if (output_bytes > 16 * 1024 * 1024) return Error("DASH 화질 선택 정보가 지원 크기를 초과했습니다.");
    base::DictValue row;
    row.Set("quality", track.quality.empty() ? std::to_string(track.bandwidth) + " bps" : track.quality);
    row.Set("parts", std::move(track.urls));
    row.Set("audioParts", audio ? audio->urls.Clone() : base::ListValue());
    row.Set("audioLanguage", audio ? audio->language : "");
    variants.Append(std::move(row));
  }
  base::DictValue result; result.Set("dashVariants", std::move(variants)); return result;
}
}
