#include "chrome/browser/internet_browser/video_youtube.h"
#include <algorithm>
#include <cmath>
#include <utility>
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/strings/string_number_conversions.h"
#include "base/time/time.h"
#include "chrome/browser/internet_browser/video_playlist.h"
#include "chrome/browser/profiles/profile.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/storage_partition.h"
#include "content/public/browser/web_contents.h"
#include "net/base/url_util.h"
#include "net/http/http_status_code.h"
#include "net/http/http_response_headers.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/network/public/cpp/resource_request.h"
#include "services/network/public/cpp/simple_url_loader.h"
#include "services/network/public/cpp/shared_url_loader_factory.h"
#include "services/network/public/mojom/fetch_api.mojom.h"
#include "services/network/public/mojom/url_response_head.mojom.h"

namespace internet_browser {
namespace {
bool Cdn(const GURL& url) {
  return url.is_valid() && url.SchemeIs("https") && url.DomainIs("googlevideo.com") &&
      !url.has_username() && !url.has_password() && !url.has_ref() &&
      (url.port().empty() || url.port() == "443") && url.spec().size() <= 16384;
}
bool Manifest(const GURL& url) { return Cdn(url) && url.host() == "manifest.googlevideo.com"; }
}
YoutubeVideo::YoutubeVideo(Profile* profile, content::WeakDocumentPtr document, GURL source)
    : profile_(profile), document_(document), source_(std::move(source)), video_id_(VideoId(source_)) {}
YoutubeVideo::~YoutubeVideo() = default;
std::string YoutubeVideo::VideoId(const GURL& source) {
  if (!source.SchemeIs("https") || source.has_username() || source.has_password() ||
      (source.host() != "www.youtube.com" && source.host() != "youtube.com" && source.host() != "m.youtube.com") ||
      (!source.port().empty() && source.port() != "443")) return {};
  std::string id;
  if (source.path() == "/watch") net::GetValueForKeyInQuery(source, "v", &id);
  else for (const auto* prefix : {"/shorts/", "/embed/", "/live/"})
    if (source.path().starts_with(prefix)) { id = source.path().substr(std::string(prefix).size()); break; }
  if (id.size() != 11 || !std::all_of(id.begin(), id.end(), [](unsigned char c) {
        return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
      })) return {};
  return id;
}
bool YoutubeVideo::Current() const {
  auto* frame = document_.AsRenderFrameHostIfValid();
  return frame && frame->IsActive() && frame->IsRenderFrameLive() && !profile_->IsOffTheRecord() &&
      frame->GetLastCommittedURL().GetWithoutRef() == source_.GetWithoutRef() &&
      content::WebContents::FromRenderFrameHost(frame)->GetBrowserContext() == profile_ && !video_id_.empty();
}
void YoutubeVideo::Discover(const std::string& visitor, const base::DictValue* size_hints, Reply reply) {
  reply_ = std::move(reply);
  if (!Current() || visitor.empty() || visitor.size() > 4096) {
    Fail("YouTube 페이지를 새로고침한 뒤 영상을 다시 찾아 주세요."); return;
  }
  if (size_hints && size_hints->size() <= 60) for (const auto [key, value] : *size_hints) {
    const auto bytes = value.GetIfDouble();
    if (key.size() <= 80 && bytes && std::isfinite(*bytes) && *bytes > 0 && *bytes <= 9007199254740991.0)
      size_hints_.Set(key, *bytes);
  }
  base::DictValue client;
  client.Set("clientName", "VISIONOS"); client.Set("clientVersion", "1.02");
  client.Set("deviceMake", "Apple"); client.Set("deviceModel", "RealityDevice17,1");
  client.Set("osName", "visionOS"); client.Set("osVersion", "26.5.23O471");
  client.Set("hl", "ko"); client.Set("timeZone", "UTC"); client.Set("utcOffsetMinutes", 0);
  client.Set("visitorData", visitor);
  base::DictValue context; context.Set("client", std::move(client));
  base::DictValue playback; playback.Set("html5Preference", "HTML5_PREF_WANTS");
  base::DictValue playback_context; playback_context.Set("contentPlaybackContext", std::move(playback));
  base::DictValue request; request.Set("context", std::move(context)); request.Set("videoId", video_id_);
  request.Set("playbackContext", std::move(playback_context));
  std::string body; base::JSONWriter::Write(request, &body);
  Fetch(GURL("https://www.youtube.com/youtubei/v1/player?prettyPrint=false"), Phase::kPlayer, std::move(body));
}
void YoutubeVideo::Resolve(GURL video, GURL audio, Reply reply) {
  reply_ = std::move(reply); audio_ = std::move(audio);
  if (!Current() || !Manifest(video) || (!audio_.is_empty() && !Manifest(audio_))) {
    Fail("YouTube 영상 주소가 만료되었거나 올바르지 않습니다. 다시 검사해 주세요."); return;
  }
  Fetch(std::move(video), Phase::kVideo);
}
void YoutubeVideo::Fetch(GURL url, Phase phase, std::string body) {
  if (!Current()) { Fail("원본 영상 페이지가 닫히거나 바뀌었습니다. 다시 검사해 주세요."); return; }
  auto request = std::make_unique<network::ResourceRequest>(); request->url = url;
  request->credentials_mode = network::mojom::CredentialsMode::kOmit;
  request->redirect_mode = network::mojom::RedirectMode::kError;
  if (phase == Phase::kPlayer) {
    request->method = "POST";
    request->headers.SetHeader("X-YouTube-Client-Name", "101");
    request->headers.SetHeader("X-YouTube-Client-Version", "1.02");
    request->headers.SetHeader("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15");
  } else if (!Manifest(url)) { Fail("지원하지 않는 YouTube 재생 목록 주소입니다."); return; }
  const auto annotation = net::DefineNetworkTrafficAnnotation("internet_browser_youtube_hls", R"(
    semantics {
      sender: "Internet Browser YouTube video discovery"
      description: "Obtains public HLS qualities for the exact YouTube video selected by the user."
      trigger: "User inspects a detected YouTube video."
      data: "Video ID and page visitor context; no account cookies or authorization."
      destination: GOOGLE_OWNED_SERVICE
    }
    policy {
      cookies_allowed: NO
      setting: "Only on explicit video inspection; unavailable in incognito."
      policy_exception_justification: "User-initiated public video discovery."
    })");
  loader_ = network::SimpleURLLoader::Create(std::move(request), annotation);
  loader_->SetTimeoutDuration(base::Seconds(15));
  if (!body.empty()) loader_->AttachStringForUpload(body, "application/json");
  loader_->DownloadToString(profile_->GetDefaultStoragePartition()->GetURLLoaderFactoryForBrowserProcess().get(),
      base::BindOnce(&YoutubeVideo::Loaded, weak_factory_.GetWeakPtr(), url, phase), 2 * 1024 * 1024);
}
void YoutubeVideo::Loaded(GURL url, Phase phase, std::optional<std::string> body) {
  if (!Current()) { Fail("원본 영상 페이지가 닫히거나 바뀌었습니다. 다시 검사해 주세요."); return; }
  const auto* response = loader_->ResponseInfo();
  if (!body || !response || !response->headers || response->headers->response_code() != net::HTTP_OK) {
    Fail("YouTube 영상 정보를 받지 못했습니다. 잠시 후 다시 검사해 주세요."); return;
  }
  loader_.reset();
  if (phase == Phase::kPlayer) {
    auto data = base::JSONReader::ReadDict(*body, base::JSON_PARSE_RFC);
    if (!data || data->FindStringByDottedPath("playabilityStatus.status") == nullptr ||
        *data->FindStringByDottedPath("playabilityStatus.status") != "OK" ||
        data->FindStringByDottedPath("videoDetails.videoId") == nullptr ||
        *data->FindStringByDottedPath("videoDetails.videoId") != video_id_) {
      Fail("이 YouTube 영상은 공개된 일반 영상으로 확인되지 않았습니다. 로그인·연령 확인·생방송 영상은 이 경로로 저장할 수 없습니다."); return;
    }
    const auto* address = data->FindStringByDottedPath("streamingData.hlsManifestUrl");
    if (!address || !Manifest(GURL(*address))) {
      Fail("이 영상의 저장 가능한 HLS 화질을 확인하지 못했습니다."); return;
    }
    if (const auto* duration = data->FindStringByDottedPath("videoDetails.lengthSeconds"))
      base::StringToDouble(*duration, &duration_seconds_);
    Fetch(GURL(*address), Phase::kMaster); return;
  }
  const auto playlist = ParseVideoPlaylist(*body, phase == Phase::kMaster);
  if (!playlist.error.empty()) { Fail(playlist.error.c_str()); return; }
  if (phase == Phase::kMaster) {
    base::ListValue variants;
    auto ordered = playlist.variants;
    const auto height = [](const VideoPlaylistPart& item) {
      int value = 0; const auto x = item.quality.find('x');
      if (x != std::string::npos) base::StringToInt(item.quality.substr(x + 1), &value);
      return value;
    };
    std::stable_sort(ordered.begin(), ordered.end(), [&](const auto& a, const auto& b) { return height(a) > height(b); });
    for (const auto& item : ordered) {
      // The existing converter supports H.264/AAC, not arbitrary YouTube codecs.
      if (item.codecs.find("avc1.") == std::string::npos || item.codecs.find("mp4a.") == std::string::npos) continue;
      const GURL video = url.Resolve(item.address);
      const GURL audio = item.audio_address.empty() ? GURL() : url.Resolve(item.audio_address);
      if (!Manifest(video) || (!audio.is_empty() && !Manifest(audio))) continue;
      std::string quality = height(item) > 0 ? base::NumberToString(height(item)) + "p" : item.quality;
      double fps = 0;
      if (base::StringToDouble(item.frame_rate, &fps) && std::isfinite(fps) && fps > 30 && fps <= 240)
        quality += base::NumberToString(static_cast<int>(std::round(fps)));
      base::DictValue row; row.Set("url", video.spec()); row.Set("audioUrl", audio.spec());
      row.Set("quality", quality); row.Set("audioLanguage", item.audio_language); row.Set("kind", "youtube_hls");
      double bytes = size_hints_.FindDouble(quality).value_or(0);
      if (bytes <= 0) {
        double bitrate = 0;
        if (base::StringToDouble(item.bandwidth, &bitrate) && bitrate > 0 && duration_seconds_ > 0)
          bytes = bitrate * duration_seconds_ / 8;
      }
      if (std::isfinite(bytes) && bytes > 0 && bytes <= 9007199254740991.0) {
        row.Set("sizeBytes", bytes); row.Set("sizeEstimated", true);
      }
      variants.Append(std::move(row));
    }
    if (variants.empty()) { Fail("이 영상에는 현재 저장할 수 있는 H.264/AAC HLS 화질이 없습니다."); return; }
    base::DictValue result; result.Set("variants", std::move(variants)); Finish(std::move(result)); return;
  }
  if (!playlist.variants.empty()) { Fail("영상 구간 대신 중첩된 재생 목록을 받았습니다. 다시 검사해 주세요."); return; }
  std::vector<GURL> parts; size_t bytes = 0;
  for (const auto& item : playlist.parts) {
    auto address = url.Resolve(item.address); bytes += address.spec().size();
    if (!Cdn(address) || bytes > 8 * 1024 * 1024) { Fail("영상 구간 주소가 지원 범위를 초과합니다."); return; }
    parts.push_back(std::move(address));
  }
  if (phase == Phase::kVideo) {
    video_parts_ = std::move(parts); transport_ = playlist.extension == ".ts";
    if (!audio_.is_empty()) { Fetch(audio_, Phase::kAudio); return; }
  } else if (transport_ != (playlist.extension == ".ts")) {
    Fail("영상과 음성의 구간 형식이 달라 현재 함께 저장할 수 없습니다."); return;
  }
  if (video_parts_.size() + (phase == Phase::kAudio ? parts.size() : 0) > 20000) {
    Fail("영상과 음성 구간의 합계가 지원 범위를 초과합니다."); return;
  }
  base::ListValue video_rows, audio_rows;
  for (const auto& part : video_parts_) video_rows.Append(part.spec());
  if (phase == Phase::kAudio) for (const auto& part : parts) audio_rows.Append(part.spec());
  base::DictValue variant; variant.Set("parts", std::move(video_rows)); variant.Set("audioParts", std::move(audio_rows));
  variant.Set("transportStream", transport_);
  base::ListValue ready; ready.Append(std::move(variant));
  base::DictValue result; result.Set("dashVariants", std::move(ready)); Finish(std::move(result));
}
void YoutubeVideo::Finish(base::DictValue result) {
  done_ = true; loader_.reset();
  if (reply_) std::move(reply_).Run(std::move(result));
}
void YoutubeVideo::Fail(const char* reason) { base::DictValue result; result.Set("error", reason); Finish(std::move(result)); }
}
