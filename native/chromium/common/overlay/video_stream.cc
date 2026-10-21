#include "chrome/browser/internet_browser/video_stream.h"
#include <array>
#include <utility>
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/important_file_writer.h"
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/task/thread_pool.h"
#include "base/task/sequenced_task_runner.h"
#include "base/time/time.h"
#include "base/unguessable_token.h"
#include "chrome/browser/internet_browser/video_playlist.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/browser/profiles/profile.h"
#include "content/public/browser/download_manager.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"
#include "net/traffic_annotation/network_traffic_annotation.h"

namespace internet_browser {
namespace {
constexpr auto kTraffic = net::DefineNetworkTrafficAnnotation("internet_browser_video_stream", R"(
 semantics {
   sender: "Internet Browser video stream saver"
   description: "Saves a user-selected non-encrypted video playlist and its media parts."
   trigger: "User selects Inspect or Save in the video section."
   data: "Observed video addresses and ordinary source-frame download headers."
   destination: WEBSITE
 }
 policy {
   cookies_allowed: YES
   cookies_store: "user"
   setting: "Only runs after an explicit user request."
   policy_exception_justification: "Uses the standard browser download path and safety checks."
 })");
bool Directory(base::FilePath result) {
  const auto parent = result.DirName();
  if (!base::CreateDirectory(parent) || base::IsLink(parent) ||
      base::PathExists(result)) return false;
  return base::CreateDirectory(result);
}
bool AppendPart(base::FilePath part, base::FilePath output, bool first) {
  base::File input(part, base::File::FLAG_OPEN | base::File::FLAG_READ);
  if (!input.IsValid() || base::IsLink(part)) return false;
  const auto length = input.GetLength();
  if (length < 8 || length > 256 * 1024 * 1024) return false;
  if (first) {
    std::string init;
    if (!base::ReadFileToStringWithMaxSize(part, &init, 8 * 1024 * 1024) ||
        init.substr(4, 4) != "ftyp" || init.find("pssh") != std::string::npos || init.find("tenc") != std::string::npos) return false;
  }
  // Windows append-only handles cannot reliably FlushFileBuffers. Use a write
  // handle and seek on this job's single sequenced worker instead.
  base::File destination(output, base::File::FLAG_OPEN_ALWAYS | base::File::FLAG_WRITE);
  if (!destination.IsValid() || destination.Seek(base::File::FROM_END, 0) < 0) return false;
  std::array<uint8_t, 65536> buffer;
  while (true) {
    const auto count = input.ReadAtCurrentPos(buffer);
    if (!count) return false;
    if (!*count) break;
    if (!destination.WriteAtCurrentPosAndCheck(base::span(buffer).first(*count))) return false;
  }
  const bool flushed = destination.Flush();
  input.Close();
  destination.Close();
  return flushed && base::DeleteFile(part);
}
bool Finalize(base::FilePath directory, std::string title, std::string page) {
  const auto file = directory.AppendASCII("video.mp4");
  const auto partial = directory.AppendASCII("video.part");
  if (!base::Move(partial, file)) return false;
  base::DictValue entry; entry.Set("title", title); entry.Set("sourcePage", page);
  std::string json;
  return base::JSONWriter::Write(entry, &json) && base::ImportantFileWriter::WriteFileAtomically(directory.AppendASCII("complete.json"), json);
}
void ForgetDownload(Profile* profile, download::DownloadItem* item, bool cancel) {
  // Remove()/Cancel() notify observers themselves. Never call them from an
  // OnDownloadUpdated notification (DownloadItem explicitly forbids reentry).
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
      base::BindOnce([](base::WeakPtr<Profile> profile, std::string guid, bool cancel) {
        if (!profile) return;
        auto* item = profile->GetDownloadManager()->GetDownloadByGuid(guid);
        if (!item) return;
        if (cancel) item->Cancel(false);
        item->Remove();
      }, profile->GetWeakPtr(), item->GetGuid(), cancel));
}
}
VideoStream::VideoStream(Profile* profile, content::WeakDocumentPtr document, std::string title, std::string page)
    : profile_(profile), document_(document), title_(std::move(title)), page_(std::move(page)),
      id_("stream:" + base::UnguessableToken::Create().ToString()),
      worker_(base::ThreadPool::CreateSequencedTaskRunner({base::MayBlock(), base::TaskShutdownBehavior::BLOCK_SHUTDOWN})) {
  directory_ = profile->GetPath().AppendASCII("InternetBrowserVideos").AppendASCII("stream-" + id_.substr(7));
  if (auto* frame = document_.AsRenderFrameHostIfValid()) source_url_ = frame->GetLastCommittedURL().GetWithoutRef();
}
VideoStream::~VideoStream() {
  if (observation_.IsObserving()) { auto* item = observation_.GetSource(); observation_.Reset(); ForgetDownload(profile_, item, true); }
  if (state_ != 1) Cleanup();
}
void VideoStream::Inspect(GURL manifest, Reply reply) {
  inspect_ = true;
  base::SequencedTaskRunner::GetCurrentDefault()->PostDelayedTask(FROM_HERE,
      base::BindOnce([](base::WeakPtr<VideoStream> job) {
        if (job && job->state_ == 0) job->Fail("스트림 확인 시간이 초과되었습니다. 원본 탭을 확인하고 다시 시도해 주세요.");
      }, weak_factory_.GetWeakPtr()), base::Seconds(30));
  worker_->PostTaskAndReplyWithResult(FROM_HERE,
      base::BindOnce(&Directory, directory_), base::BindOnce(&VideoStream::DirectoryReady,
      weak_factory_.GetWeakPtr(), true, std::move(manifest), std::move(reply)));
}
void VideoStream::Start(std::vector<GURL> parts, Reply reply) {
  parts_ = std::move(parts);
  worker_->PostTaskAndReplyWithResult(FROM_HERE,
      base::BindOnce(&Directory, directory_), base::BindOnce(&VideoStream::DirectoryReady,
      weak_factory_.GetWeakPtr(), false, GURL(), std::move(reply)));
}
void VideoStream::DirectoryReady(bool inspect, GURL manifest, Reply reply, bool created) {
  reply_ = std::move(reply);
  if (!created) { Fail("영상 저장 폴더를 만들지 못했습니다."); return; }
  if (state_ != 0) { Fail("영상 저장이 취소되었습니다."); return; }
  if (inspect) Fetch(manifest, directory_.AppendASCII("manifest.m3u8"));
  else {
    base::DictValue result; result.Set("started", true); result.Set("guid", id_);
    std::move(reply_).Run(std::move(result)); NextPart();
  }
}
void VideoStream::Fetch(const GURL& url, const base::FilePath& target) {
  auto* frame = document_.AsRenderFrameHostIfValid();
  if (!frame || !frame->IsActive() || frame->GetLastCommittedURL().GetWithoutRef() != source_url_ ||
      content::WebContents::FromRenderFrameHost(frame)->GetBrowserContext() != profile_) {
    Fail("원본 페이지가 닫히거나 바뀌어 스트림 저장을 중단했습니다."); return;
  }
  if (!url.is_valid() || !url.SchemeIsHTTPOrHTTPS() || url.has_username() || url.has_password()) {
    Fail("지원하지 않는 영상 구간 주소입니다."); return;
  }
  auto parameters = frame->CreateDownloadUrlParameters(url, kTraffic);
  parameters->set_file_path(target);
  parameters->set_transient(true);
  parameters->set_require_safety_checks(true);
  parameters->set_content_initiated(false);
  parameters->set_callback(base::BindOnce(&VideoStream::Started, weak_factory_.GetWeakPtr()));
  profile_->GetDownloadManager()->DownloadUrl(std::move(parameters));
}
void VideoStream::Started(download::DownloadItem* item, download::DownloadInterruptReason reason) {
  if (state_ != 0) { if (item) ForgetDownload(profile_, item, true); return; }
  if (!item || reason != download::DOWNLOAD_INTERRUPT_REASON_NONE) { Fail("영상 구간 다운로드를 시작하지 못했습니다."); return; }
  observation_.Observe(item);
  OnDownloadUpdated(item);
}
void VideoStream::OnDownloadUpdated(download::DownloadItem* item) {
  if (item->IsDangerous() || item->IsInsecure() || item->GetReceivedBytes() > (inspect_ ? 2 * 1024 * 1024 : 256 * 1024 * 1024)) {
    Fail("안전 검사 또는 구간 크기 제한으로 영상 저장을 중단했습니다."); return;
  }
  if (item->GetState() == download::DownloadItem::COMPLETE) {
    const auto path = item->GetTargetFilePath(); const auto url = item->GetURL();
    received_ += item->GetReceivedBytes();
    observation_.Reset(); ForgetDownload(profile_, item, false);
    waiting_ = true;
    base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
        base::BindOnce(&VideoStream::PartReady, weak_factory_.GetWeakPtr(), path, url));
  } else if (item->GetState() == download::DownloadItem::CANCELLED) Fail("영상 저장이 취소되었습니다.");
  else if (item->GetState() == download::DownloadItem::INTERRUPTED) {
    if (inspect_) { Fail("스트림 정보를 내려받지 못했습니다. 원본 페이지에서 영상을 재생한 뒤 다시 시도해 주세요."); return; }
    error_ = "네트워크 오류로 중단되었습니다. 재개를 눌러 다시 시도하세요."; paused_ = true;
  }
}
void VideoStream::OnDownloadDestroyed(download::DownloadItem* item) {
  observation_.Reset(); Fail("영상 다운로드가 종료되었습니다.");
}
void VideoStream::PartReady(base::FilePath path, GURL final_url) {
  if (state_ != 0) return;
  if (path.DirName() != directory_) { waiting_ = false; Fail("영상 구간 저장 경로가 일치하지 않습니다."); return; }
  if (inspect_) {
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce([](base::FilePath path) { std::string text; base::ReadFileToStringWithMaxSize(path, &text, 2 * 1024 * 1024); return text; }, path),
        base::BindOnce(&VideoStream::Inspected, weak_factory_.GetWeakPtr(), final_url));
  } else {
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce(&AppendPart, path, directory_.AppendASCII("video.part"), completed_ == 0),
        base::BindOnce(&VideoStream::Appended, weak_factory_.GetWeakPtr()));
  }
}
void VideoStream::Inspected(GURL final_url, std::string body) {
  waiting_ = false;
  if (!base::IsStringUTF8(body)) { Fail("올바른 UTF-8 스트림 재생 목록이 아닙니다."); return; }
  auto playlist = ParseVideoPlaylist(body);
  if (!playlist.error.empty()) { Fail(playlist.error.c_str()); return; }
  base::DictValue result; base::ListValue variants, parts;
  for (const auto& item : playlist.variants) {
    base::DictValue row; row.Set("url", final_url.Resolve(item.address).spec()); row.Set("quality", item.quality); variants.Append(std::move(row));
  }
  if (playlist.variants.empty() && playlist.extension != ".mp4") {
    Fail("이 HLS 영상은 MPEG-TS 변환이 필요합니다. 현재는 MP4 구간으로 구성된 HLS 영상만 저장할 수 있습니다."); return;
  }
  size_t address_bytes = 0;
  for (const auto& item : playlist.parts) {
    const auto address = final_url.Resolve(item.address).spec();
    address_bytes += address.size();
    if (address.size() > 16384 || address_bytes > 8 * 1024 * 1024) {
      Fail("영상 구간 정보가 지원 크기를 초과했습니다."); return;
    }
    parts.Append(address);
  }
  result.Set("variants", std::move(variants)); result.Set("parts", std::move(parts));
  state_ = 1; waiting_ = false;
  Cleanup();
  if (reply_) std::move(reply_).Run(std::move(result));
}
void VideoStream::Appended(bool success) {
  waiting_ = false;
  if (state_ != 0) { Cleanup(); return; }
  if (!success) { Fail("MP4 구간을 저장하지 못했습니다. 보호되거나 지원하지 않는 영상일 수 있습니다."); return; }
  if (received_ > 8.0 * 1024 * 1024 * 1024) { Fail("영상이 현재 저장 크기 제한인 8 GB를 초과했습니다."); return; }
  ++completed_;
  if (completed_ == parts_.size()) {
    waiting_ = true;
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce(&Finalize, directory_, title_, page_), base::BindOnce(&VideoStream::Finalized, weak_factory_.GetWeakPtr()));
  } else if (!paused_) NextPart();
}
void VideoStream::NextPart() {
  if (state_ != 0 || paused_ || waiting_ || observation_.IsObserving()) return;
  if (completed_ >= parts_.size()) { Fail("영상 구간 정보가 없습니다."); return; }
  Fetch(parts_[completed_], directory_.AppendASCII("part-" + base::UnguessableToken::Create().ToString() + ".mp4"));
}
void VideoStream::Finalized(bool success) {
  waiting_ = false;
  if (state_ != 0) { Cleanup(); return; }
  if (!success) { Fail("완성된 영상을 서재에 등록하지 못했습니다."); return; }
  state_ = 1; paused_ = false;
}
base::DictValue VideoStream::Status() const {
  auto result = base::DictValue(); result.Set("guid", id_); result.Set("name", title_);
  result.Set("inspection", inspect_);
  result.Set("state", state_); result.Set("paused", paused_); result.Set("blocked", false);
  result.Set("canResume", state_ == 0 && paused_); result.Set("stream", true);
  result.Set("pausing", paused_ && (observation_.IsObserving() || waiting_));
  result.Set("completedParts", static_cast<int>(completed_)); result.Set("totalParts", static_cast<int>(parts_.size()));
  result.Set("received", received_ + (observation_.IsObserving() ? observation_.GetSource()->GetReceivedBytes() : 0));
  result.Set("total", 0); result.Set("error", error_); return result;
}
bool VideoStream::Control(const std::string& action) {
  if (state_ != 0 || inspect_) return false;
  if (action == "cancel") { state_ = 2; Fail("영상 저장이 취소되었습니다."); return true; }
  // Pause between complete parts. Rapidly pausing an initializing download
  // stream can invalidate Chromium's data pipe before its first read; keeping
  // part downloads atomic also makes retries deterministic.
  if (action == "pause") { paused_ = true; return true; }
  if (action == "resume") {
    paused_ = false; error_.clear();
    if (observation_.IsObserving() && observation_.GetSource()->GetState() == download::DownloadItem::INTERRUPTED) {
      auto* item = observation_.GetSource(); observation_.Reset(); ForgetDownload(profile_, item, true);
    }
    NextPart();
    return true;
  }
  return false;
}
void VideoStream::Fail(const char* error) {
  if (state_ != 2) state_ = 3;
  error_ = error; paused_ = false;
  if (observation_.IsObserving()) { auto* item = observation_.GetSource(); observation_.Reset(); ForgetDownload(profile_, item, true); }
  if (reply_) { base::DictValue result; result.Set("error", error_); std::move(reply_).Run(std::move(result)); }
  if (!waiting_) Cleanup();
}
void VideoStream::Cleanup() {
  if (directory_.empty()) return;
  auto directory = directory_;
  // Queue behind any UI-thread download cancellation/removal, then serialize
  // deletion behind this job's outstanding file operations.
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
      base::BindOnce([](scoped_refptr<base::SequencedTaskRunner> worker, base::FilePath directory) {
        worker->PostTask(FROM_HERE,
            base::BindOnce([](base::FilePath path) { base::DeletePathRecursively(path); }, directory));
      }, worker_, directory));
}
}
