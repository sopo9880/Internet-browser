#include "chrome/browser/internet_browser/video_capture.h"
#include <algorithm>
#include <memory>
#include <utility>
#include <vector>
#include "base/functional/bind.h"
#include "base/strings/utf_string_conversions.h"
#include "base/task/sequenced_task_runner.h"
#include "base/time/time.h"
#include "base/unguessable_token.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/video_file_types.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/browser/internet_browser/video_stream.h"
#include "chrome/browser/internet_browser/video_youtube.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/tab_contents/tab_contents_iterator.h"
#include "chrome/common/chrome_isolated_world_ids.h"
#include "components/download/public/common/download_item.h"
#include "components/download/public/common/download_url_parameters.h"
#include "components/tabs/public/tab_interface.h"
#include "content/public/browser/download_manager.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "url/gurl.h"

namespace internet_browser {
namespace {
base::DictValue Error(const char* message) {
  base::DictValue result; result.Set("error", message); return result;
}
bool Remote(const GURL& url) {
  return url.is_valid() && url.SchemeIsHTTPOrHTTPS() && !url.has_username() && !url.has_password();
}
}
VideoCapture::VideoCapture(Profile* profile) : profile_(profile) { profile_observation_.Observe(profile); }
VideoCapture::~VideoCapture() = default;
void VideoCapture::OnProfileWillBeDestroyed(Profile*) {
  scan_factory_.InvalidateWeakPtrs(); weak_factory_.InvalidateWeakPtrs();
  scan_reply_.Reset(); candidates_.clear();
  for (const auto& stream : streams_) stream->Shutdown();
  streams_.clear(); profile_observation_.Reset();
  youtube_.clear();
}
VideoCapture* VideoCapture::Get(Profile* profile) {
  static constexpr char key[] = "internet-browser-video-capture";
  auto* value = static_cast<VideoCapture*>(profile->GetUserData(key));
  if (!value) {
    auto owned = std::make_unique<VideoCapture>(profile); value = owned.get();
    profile->SetUserData(key, std::move(owned));
  }
  return value;
}
void VideoCapture::Scan(Reply reply) {
  if (scan_reply_) { std::move(reply).Run(Error("영상 검사 중입니다. 잠시 기다려 주세요.")); return; }
  scan_factory_.InvalidateWeakPtrs();
  candidates_.clear(); found_.clear(); reasons_.clear();
  scan_reply_ = std::move(reply);
  std::vector<content::WeakDocumentPtr> documents;
  tabs::ForEachTabInterface([&](tabs::TabInterface* tab) {
    auto* contents = tab->GetContents();
    if (!contents || contents->GetBrowserContext() != profile_ || !Remote(contents->GetLastCommittedURL())) return true;
    contents->ForEachRenderFrameHost([&](content::RenderFrameHost* frame) {
      if (documents.size() < 100 && frame->IsRenderFrameLive() && frame->IsActive() && Remote(frame->GetLastCommittedURL()))
        documents.push_back(frame->GetWeakDocumentPtr());
    });
    return documents.size() < 100;
  });
  pending_ = documents.size();
  if (!pending_) { FinishScan(); return; }
  base::SequencedTaskRunner::GetCurrentDefault()->PostDelayedTask(FROM_HERE,
      base::BindOnce(&VideoCapture::FinishScan, scan_factory_.GetWeakPtr()), base::Seconds(15));
  for (const auto& document : documents) {
    auto* frame = document.AsRenderFrameHostIfValid();
    if (!frame) { if (!--pending_) FinishScan(); continue; }
    frame->ExecuteJavaScriptInIsolatedWorld(base::UTF8ToUTF16(std::string(kVideoDiscoveryJs)),
        base::BindOnce(&VideoCapture::Scanned, scan_factory_.GetWeakPtr(), document),
        ISOLATED_WORLD_ID_CHROME_INTERNAL);
  }
}
void VideoCapture::Scanned(content::WeakDocumentPtr document, base::Value value) {
  if (!scan_reply_) return;
  auto* frame = document.AsRenderFrameHostIfValid();
  const auto* data = value.GetIfDict();
  const auto* snapshot_url = data ? data->FindString("documentUrl") : nullptr;
  if (frame && frame->IsActive() && data && snapshot_url &&
      GURL(*snapshot_url).GetWithoutRef() == frame->GetLastCommittedURL().GetWithoutRef() &&
      content::WebContents::FromRenderFrameHost(frame)->GetBrowserContext() == profile_) {
    if (const auto* items = data->FindList("items")) {
      for (const auto& entry : *items) {
        if (candidates_.size() >= 200) break;
        const auto* item = entry.GetIfDict();
        if (!item) continue;
        const auto* address = item->FindString("url");
        const auto* kind = item->FindString("kind");
        if (!address || address->size() > 16384 || !Remote(GURL(*address)) || !kind ||
            (*kind != "file" && *kind != "hls" && *kind != "dash" && *kind != "pair" && *kind != "youtube")) continue;
        if (*kind == "youtube" && (YoutubeVideo::VideoId(frame->GetLastCommittedURL()).empty() ||
            GURL(*address).GetWithoutRef() != frame->GetLastCommittedURL().GetWithoutRef())) continue;
        auto row = item->Clone();
        std::vector<GURL> video_parts, audio_parts;
        const auto* mime = item->FindString("mime");
        const auto source_path = base::ToLowerASCII(GURL(*address).path());
        const bool transport = *kind == "file" && (source_path.ends_with(".ts") || source_path.ends_with(".m2ts") || (mime && *mime == "video/mp2t"));
        if (*kind == "pair") {
          const auto* audio = item->FindString("audioUrl");
          if (!audio || audio->size() > 16384 || !Remote(GURL(*audio))) continue;
          video_parts.emplace_back(*address); audio_parts.emplace_back(*audio);
          row.Set("kind", "stream"); row.Set("paired", true);
        } else if (transport) {
          video_parts.emplace_back(*address); row.Set("kind", "stream"); row.Set("convertedFromTs", true);
        }
        row.Set("title", NormalizeVideoTitle(item->FindString("title") ? *item->FindString("title") : "영상"));
        row.Set("page", content::WebContents::FromRenderFrameHost(frame)->GetLastCommittedURL().spec());
        const auto token = base::UnguessableToken::Create().ToString();
        row.Set("token", token);
        candidates_.emplace(token, Candidate{document, frame->GetLastCommittedURL().GetWithoutRef(), row.Clone(), std::move(video_parts), std::move(audio_parts), transport});
        row.Remove("visitorData"); row.Remove("sizeHints"); found_.Append(std::move(row));
      }
    }
    if (const auto* reasons = data->FindList("reasons"))
      for (const auto& reason : *reasons)
        if (reason.is_string() && reason.GetString().size() < 1024 && reasons_.size() < 20) reasons_.insert(reason.GetString());
  }
  if (pending_ && !--pending_) FinishScan();
}
void VideoCapture::FinishScan() {
  if (!scan_reply_) return;
  scan_factory_.InvalidateWeakPtrs();
  base::DictValue result;
  result.Set("partial", pending_ != 0);
  result.Set("items", std::move(found_));
  base::ListValue reasons;
  for (const auto& reason : reasons_) reasons.Append(reason);
  result.Set("reasons", std::move(reasons));
  pending_ = 0;
  std::move(scan_reply_).Run(std::move(result));
}
void VideoCapture::Download(const std::string& token, Reply reply) {
  const auto it = candidates_.find(token);
  if (it == candidates_.end()) { std::move(reply).Run(Error("영상을 다시 검사한 뒤 선택해 주세요.")); return; }
  const auto& candidate = it->second;
  auto* frame = candidate.document.AsRenderFrameHostIfValid();
  if (!frame || !frame->IsActive() || frame->GetLastCommittedURL().GetWithoutRef() != candidate.source_url ||
      content::WebContents::FromRenderFrameHost(frame)->GetBrowserContext() != profile_) {
    std::move(reply).Run(Error("원본 페이지가 닫히거나 바뀌었습니다. 다시 검사해 주세요.")); return;
  }
  if (*candidate.data.FindString("kind") == "stream") {
    if (profile_->IsOffTheRecord()) { std::move(reply).Run(Error("시크릿 창에서는 스트림 서재 저장을 지원하지 않습니다.")); return; }
    std::erase_if(streams_, [](const auto& job) { const auto status = job->Status(); return status.FindBool("inspection").value_or(false) && status.FindInt("state").value_or(0) != 0; });
    const auto active = std::count_if(streams_.begin(), streams_.end(), [](const auto& job) { return job->Status().FindInt("state").value_or(0) == 0; });
    if (active >= 4) { std::move(reply).Run(Error("동시에 저장할 수 있는 스트림은 4개입니다. 진행 중인 저장을 마친 뒤 다시 시도해 주세요.")); return; }
    if (streams_.size() >= 30) {
      const auto old = std::find_if(streams_.begin(), streams_.end(), [](const auto& job) { return job->Status().FindInt("state").value_or(0) != 0; });
      if (old != streams_.end()) streams_.erase(old);
    }
    auto job = std::make_unique<VideoStream>(profile_, candidate.document, *candidate.data.FindString("title"), *candidate.data.FindString("page"));
    auto* pointer = job.get(); streams_.push_back(std::move(job));
    pointer->Start(candidate.parts, std::move(reply), candidate.audio_parts, candidate.transport_stream); return;
  }
  if (*candidate.data.FindString("kind") != "file") {
    std::move(reply).Run(Error("먼저 스트림 확인을 눌러 저장 가능한 화질을 선택해 주세요.")); return;
  }
  const GURL url(*candidate.data.FindString("url"));
  const auto annotation = net::DefineNetworkTrafficAnnotation("internet_browser_video_download", R"(
    semantics {
      sender: "Internet Browser video downloads"
      description: "Downloads a video discovered in an open page after the user selects Save."
      trigger: "User selects a detected video and presses Save."
      data: "Video URL and ordinary source-page download request headers."
      destination: WEBSITE
    }
    policy {
      cookies_allowed: YES
      cookies_store: "user"
      setting: "Only performed on explicit user request."
      policy_exception_justification: "Uses standard browser download policies."
    })");
  auto parameters = frame->CreateDownloadUrlParameters(url, annotation);
  parameters->set_content_initiated(false);
  parameters->set_require_safety_checks(true);
  const std::string mime = candidate.data.FindString("mime") ? *candidate.data.FindString("mime") : "";
  std::string extension = mime == "video/unknown" ? "" : mime.find("webm") != std::string::npos ? ".webm" : ".mp4";
  const auto path = base::FilePath::FromUTF8Unsafe(url.path());
  if (IsVideoFileName(path.AsUTF8Unsafe())) {
    const auto dot = path.AsUTF8Unsafe().find_last_of('.');
    if (dot != std::string::npos) extension = path.AsUTF8Unsafe().substr(dot);
  }
  std::string name = *candidate.data.FindString("title");
  for (char& c : name) if (static_cast<unsigned char>(c) < 32 || std::string("\\/:*?\"<>|").find(c) != std::string::npos) c = '_';
  if (name.empty()) name = "video";
  parameters->set_suggested_name(base::UTF8ToUTF16(name + extension));
  parameters->set_callback(base::BindOnce([](Reply reply, download::DownloadItem* item, download::DownloadInterruptReason reason) {
    base::DictValue result;
    result.Set("started", item && reason == download::DOWNLOAD_INTERRUPT_REASON_NONE);
    if (item) result.Set("guid", item->GetGuid());
    if (!item || reason != download::DOWNLOAD_INTERRUPT_REASON_NONE) result.Set("error", "다운로드를 시작하지 못했습니다. 다운로드 화면을 확인해 주세요.");
    std::move(reply).Run(std::move(result));
  }, std::move(reply)));
  profile_->GetDownloadManager()->DownloadUrl(std::move(parameters));
}
void VideoCapture::Inspect(const std::string& token, Reply reply) {
  const auto it = candidates_.find(token);
  if (it == candidates_.end()) { std::move(reply).Run(Error("영상을 다시 검사해 주세요.")); return; }
  if (candidates_.size() >= 400) { std::move(reply).Run(Error("검사 항목이 많습니다. 열린 페이지의 영상 찾기를 다시 눌러 주세요.")); return; }
  auto* frame = it->second.document.AsRenderFrameHostIfValid();
  if (!frame || !frame->IsActive() || frame->GetLastCommittedURL().GetWithoutRef() != it->second.source_url) {
    std::move(reply).Run(Error("원본 페이지가 바뀌었습니다. 영상을 다시 검사해 주세요.")); return;
  }
  std::erase_if(streams_, [](const auto& job) { const auto status = job->Status(); return status.FindBool("inspection").value_or(false) && status.FindInt("state").value_or(0) != 0; });
  const auto active = std::count_if(streams_.begin(), streams_.end(), [](const auto& job) { return job->Status().FindInt("state").value_or(0) == 0; });
  const auto kind = *it->second.data.FindString("kind");
  if (kind == "youtube" || kind == "youtube_hls") {
    std::erase_if(youtube_, [](const auto& job) { return job->done(); });
    if (youtube_.size() >= 4 || profile_->IsOffTheRecord()) {
      std::move(reply).Run(Error("이 창에서 추가 YouTube 스트림을 확인할 수 없습니다.")); return;
    }
    auto job = std::make_unique<YoutubeVideo>(profile_, it->second.document, it->second.source_url);
    auto* pointer = job.get(); youtube_.push_back(std::move(job));
    auto callback = base::BindOnce(&VideoCapture::Inspected, weak_factory_.GetWeakPtr(), token, std::move(reply));
    if (kind == "youtube") {
      const auto* visitor = it->second.data.FindString("visitorData");
      pointer->Discover(visitor ? *visitor : std::string(), it->second.data.FindDict("sizeHints"), std::move(callback));
    } else {
      const auto* audio = it->second.data.FindString("audioUrl");
      pointer->Resolve(GURL(*it->second.data.FindString("url")), audio ? GURL(*audio) : GURL(), std::move(callback));
    }
    return;
  }
  if ((kind != "hls" && kind != "dash") || active >= 4 || profile_->IsOffTheRecord()) {
    std::move(reply).Run(Error("이 창에서 스트림을 확인할 수 없습니다.")); return;
  }
  auto job = std::make_unique<VideoStream>(profile_, it->second.document, *it->second.data.FindString("title"), *it->second.data.FindString("page"));
  auto* pointer = job.get(); streams_.push_back(std::move(job));
  pointer->Inspect(GURL(*it->second.data.FindString("url")),
      base::BindOnce(&VideoCapture::Inspected, weak_factory_.GetWeakPtr(), token, std::move(reply)), kind == "dash");
}
void VideoCapture::Inspected(std::string token, Reply reply, base::DictValue result) {
  if (result.Find("error")) { std::move(reply).Run(std::move(result)); return; }
  const auto it = candidates_.find(token);
  if (it == candidates_.end() || !it->second.document.AsRenderFrameHostIfValid() ||
      !it->second.document.AsRenderFrameHostIfValid()->IsActive() ||
      it->second.document.AsRenderFrameHostIfValid()->GetLastCommittedURL().GetWithoutRef() != it->second.source_url) {
    std::move(reply).Run(Error("검사할 페이지가 바뀌었습니다. 다시 검사해 주세요.")); return;
  }
  const auto document = it->second.document;
  const auto source_url = it->second.source_url;
  auto original = it->second.data.Clone();
  base::ListValue rows;
  if (const auto* variants = result.FindList("dashVariants")) {
    for (const auto& value : *variants) {
      if (candidates_.size() >= 400) break;
      const auto& variant = value.GetDict();
      std::vector<GURL> video, audio;
      size_t bytes = 0;
      const auto read = [&](const char* key, std::vector<GURL>& urls) {
        const auto* list = variant.FindList(key); if (!list || list->size() > 20001) return false;
        for (const auto& part : *list) {
          if (!part.is_string() || !Remote(GURL(part.GetString())) || part.GetString().size() > 16384 || (bytes += part.GetString().size()) > 16 * 1024 * 1024) return false;
          urls.emplace_back(part.GetString());
        }
        return true;
      };
      if (!read("parts", video) || !read("audioParts", audio) || video.empty()) continue;
      auto row = original.Clone(); const auto id = base::UnguessableToken::Create().ToString();
      row.Set("token", id); row.Set("kind", "stream"); row.Set("paired", !audio.empty());
      if (const auto* quality = variant.FindString("quality")) row.Set("quality", *quality);
      if (const auto* language = variant.FindString("audioLanguage"); language && !language->empty()) row.Set("audioLanguage", *language);
      const bool transport = variant.FindBool("transportStream").value_or(false);
      row.Set("convertedFromTs", transport); row.Remove("visitorData");
      candidates_.emplace(id, Candidate{document, source_url, row.Clone(), std::move(video), std::move(audio), transport});
      rows.Append(std::move(row));
    }
  }
  if (const auto* variants = result.FindList("variants")) {
    for (const auto& value : *variants) {
      const auto& variant = value.GetDict();
      const auto* address = variant.FindString("url");
      if (!address || !Remote(GURL(*address)) || candidates_.size() >= 300) continue;
      auto row = original.Clone(); row.Set("url", *address); row.Set("quality", *variant.FindString("quality"));
      if (const auto* kind = variant.FindString("kind"); kind && *kind == "youtube_hls") {
        row.Set("kind", *kind); row.Remove("visitorData"); row.Remove("sizeHints");
        if (const auto* audio = variant.FindString("audioUrl")) row.Set("audioUrl", *audio);
        if (const auto* language = variant.FindString("audioLanguage")) row.Set("audioLanguage", *language);
        if (const auto bytes = variant.FindDouble("sizeBytes")) {
          row.Set("sizeBytes", *bytes); row.Set("sizeEstimated", true);
        }
      }
      const auto id = base::UnguessableToken::Create().ToString(); row.Set("token", id);
      candidates_.emplace(id, Candidate{document, source_url, row.Clone(), {}}); rows.Append(std::move(row));
    }
  }
  if (const auto* parts = result.FindList("parts"); parts && !parts->empty()) {
    std::vector<GURL> addresses;
    for (const auto& part : *parts) {
      if (!part.is_string() || !Remote(GURL(part.GetString()))) { std::move(reply).Run(Error("지원하지 않는 영상 구간 주소입니다.")); return; }
      addresses.emplace_back(part.GetString());
    }
    auto row = original.Clone(); const auto id = base::UnguessableToken::Create().ToString();
    row.Set("token", id); row.Set("kind", "stream");
    const bool transport = result.FindBool("transportStream").value_or(false);
    row.Set("convertedFromTs", transport);
    candidates_.emplace(id, Candidate{document, source_url, row.Clone(), std::move(addresses), {}, transport}); rows.Append(std::move(row));
  }
  base::DictValue response; response.Set("items", std::move(rows)); std::move(reply).Run(std::move(response));
}
base::DictValue VideoCapture::Transfers() {
  base::DictValue result;
  base::ListValue rows;
  for (const auto& stream : streams_) {
    auto row = stream->Status();
    if (!row.FindBool("inspection").value_or(false)) rows.Append(std::move(row));
  }
  content::DownloadManager::DownloadVector items;
  profile_->GetDownloadManager()->GetAllDownloads(&items);
  for (const auto& pointer : items) {
    auto* item = pointer.get();
    if (item->IsTransient() || !IsVideoFileName(item->GetFileNameToReportUser().AsUTF8Unsafe())) continue;
    base::DictValue row;
    row.Set("guid", item->GetGuid()); row.Set("name", item->GetFileNameToReportUser().AsUTF8Unsafe());
    row.Set("state", static_cast<int>(item->GetState())); row.Set("paused", item->IsPaused());
    row.Set("received", static_cast<double>(item->GetReceivedBytes())); row.Set("total", static_cast<double>(item->GetTotalBytes()));
    row.Set("blocked", item->IsDangerous() || item->IsInsecure());
    row.Set("canResume", item->CanResume() && !item->IsDangerous() && !item->IsInsecure());
    row.Set("errorCode", static_cast<int>(item->GetLastReason()));
    rows.Append(std::move(row));
    if (rows.size() >= 100) break;
  }
  result.Set("items", std::move(rows)); return result;
}
base::DictValue VideoCapture::Control(const std::string& guid, const std::string& action) {
  if (guid.starts_with("stream:")) {
    for (const auto& stream : streams_)
      if (*stream->Status().FindString("guid") == guid) {
        if (!stream->Control(action)) return Error("이 스트림 상태를 변경할 수 없습니다.");
        return Transfers();
      }
    return Error("스트림 저장 작업을 찾을 수 없습니다.");
  }
  auto* item = profile_->GetDownloadManager()->GetDownloadByGuid(guid);
  if (!item || !IsVideoFileName(item->GetFileNameToReportUser().AsUTF8Unsafe()) || item->IsDangerous() || item->IsInsecure()) return Error("이 다운로드는 다운로드 화면에서 확인해 주세요.");
  if (action == "pause" && item->GetState() == download::DownloadItem::IN_PROGRESS) item->Pause();
  else if (action == "resume" && item->CanResume()) item->Resume(true);
  else if (action == "cancel" && item->GetState() == download::DownloadItem::IN_PROGRESS) item->Cancel(true);
  else return Error("지금은 이 작업을 수행할 수 없습니다.");
  return Transfers();
}
}
