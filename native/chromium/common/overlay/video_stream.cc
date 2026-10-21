#include "chrome/browser/internet_browser/video_stream.h"
#include <array>
#include <string_view>
#include <utility>
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/base64.h"
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/task/thread_pool.h"
#include "base/task/sequenced_task_runner.h"
#include "base/time/time.h"
#include "base/threading/platform_thread.h"
#include "base/unguessable_token.h"
#include "chrome/browser/internet_browser/video_playlist.h"
#include "chrome/browser/internet_browser/video_dash.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/common/chrome_isolated_world_ids.h"
#include "base/strings/utf_string_conversions.h"
#include "content/public/browser/download_manager.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/common/referrer.h"
#include "ui/base/page_transition_types.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/data_decoder/public/cpp/data_decoder.h"

namespace internet_browser {
namespace {
constexpr char kProcessorUrl[] = "chrome://internet-browser-transmux/";
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
bool ClearMp4(base::File& input, int64_t length) {
  int64_t offset = 0;
  for (size_t boxes = 0; offset + 8 <= length && boxes < 20000; ++boxes) {
    std::array<uint8_t, 16> header;
    if (!input.ReadAndCheck(offset, base::span(header).first<8>())) return false;
    uint64_t size = 0;
    for (const auto byte : base::span(header).first<4>()) size = (size << 8) | byte;
    const std::string_view raw(reinterpret_cast<const char*>(header.data()), header.size());
    const auto type = raw.substr(4, 4);
    size_t header_size = 8;
    if (size == 1) {
      if (!input.ReadAndCheck(offset + 8, base::span(header).subspan<8, 8>())) return false;
      size = 0; header_size = 16;
      for (const auto byte : base::span(header).subspan<8, 8>()) size = (size << 8) | byte;
    } else if (size == 0) size = length - offset;
    if (size < header_size || size > static_cast<uint64_t>(length - offset) || (!offset && type != "ftyp")) return false;
    if (type == "moov") {
      if (size > 8 * 1024 * 1024) return false;
      std::string moov(size, '\0');
      if (!input.ReadAndCheck(offset, base::as_writable_byte_span(moov))) return false;
      return moov.find("pssh") == std::string::npos && moov.find("tenc") == std::string::npos;
    }
    offset += size;
  }
  return false;
}
bool AppendPart(base::FilePath part, base::FilePath output, bool first) {
  base::File input(part, base::File::FLAG_OPEN | base::File::FLAG_READ);
  if (!input.IsValid() || base::IsLink(part)) return false;
  const auto length = input.GetLength();
  if (length < 8 || length > 8LL * 1024 * 1024 * 1024) return false;
  if (first) {
    if (!ClearMp4(input, length)) return false;
    input.Close();
    return !base::PathExists(output) && base::Move(part, output);
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
std::string ReadTransportPart(base::FilePath path) {
  std::string bytes;
  if (!base::ReadFileToStringWithMaxSize(path, &bytes, 8 * 1024 * 1024) || bytes.size() < 188) return {};
  return base::Base64Encode(bytes);
}
bool SaveTransmuxed(base::FilePath original, base::FilePath output, bool first, std::string encoded) {
  std::string bytes;
  if (encoded.size() > 24 * 1024 * 1024 || !base::Base64Decode(encoded, &bytes) || bytes.size() > 16 * 1024 * 1024) return false;
  const auto converted = original.AddExtensionASCII("converted.mp4");
  {
    base::File file(converted, base::File::FLAG_CREATE | base::File::FLAG_WRITE);
    if (!file.IsValid() || !file.WriteAtCurrentPosAndCheck(base::as_byte_span(bytes)) || !file.Flush()) return false;
  }
  return base::DeleteFile(original) && AppendPart(converted, output, first);
}
bool Finalize(base::FilePath directory, std::string title, std::string page, bool audio) {
  const auto file = directory.AppendASCII("video.mp4");
  const auto partial = directory.AppendASCII("video.part");
  if (!base::Move(partial, file)) return false;
  if (audio && !base::Move(directory.AppendASCII("audio.part"), directory.AppendASCII("audio.mp4"))) return false;
  base::DictValue entry; entry.Set("title", title); entry.Set("sourcePage", page);
  entry.Set("separateAudio", audio);
  std::string json;
  if (!base::JSONWriter::Write(entry, &json)) return false;
  // This directory is unique to the job and all writes are sequenced. A fixed
  // CREATE-only staging name avoids adding another GUID to long profile paths.
  // Publish the marker only after both media files and metadata are flushed.
  const auto staging = directory.AppendASCII("complete.part");
  {
    base::File marker(staging, base::File::FLAG_CREATE | base::File::FLAG_WRITE);
    if (!marker.IsValid() || !marker.WriteAtCurrentPosAndCheck(base::as_byte_span(json)) || !marker.Flush()) return false;
  }
  return base::Move(staging, directory.AppendASCII("complete.json"));
}
void ForgetDownload(Profile* profile, download::DownloadItem* item, bool cancel) {
  // Remove()/Cancel() notify observers themselves. Never call them from an
  // OnDownloadUpdated notification (DownloadItem explicitly forbids reentry).
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
      base::BindOnce([](base::WeakPtr<Profile> profile, std::string guid, bool cancel) {
        if (!profile) return;
        auto* manager = profile->GetDownloadManager(); if (!manager) return;
        auto* item = manager->GetDownloadByGuid(guid);
        if (!item) return;
        if (cancel) item->Cancel(false);
        item->Remove();
      }, profile->GetWeakPtr(), item->GetGuid(), cancel));
}
void DeletePartialDirectory(base::FilePath path) {
  // Windows may briefly retain a download handle on its separate file runner.
  // Retry only this job's owned directory, without blocking the UI thread.
  for (int attempt = 0; attempt < 10; ++attempt) {
    if (base::DeletePathRecursively(path)) return;
    base::PlatformThread::Sleep(base::Milliseconds(100));
  }
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
  weak_factory_.InvalidateWeakPtrs();
  ReleaseProcessor();
  if (observation_.IsObserving()) { auto* item = observation_.GetSource(); observation_.Reset(); ForgetDownload(profile_, item, true); }
  if (!shutting_down_ && state_ != 1) Cleanup();
}
void VideoStream::Shutdown() {
  shutting_down_ = true; weak_factory_.InvalidateWeakPtrs(); ReleaseProcessor();
  // Profile shutdown can happen after the UI run loop stops. There is no
  // observer notification on this stack, so cancellation must be synchronous.
  if (observation_.IsObserving()) {
    auto* item = observation_.GetSource(); observation_.Reset(); item->Cancel(false); item->Remove();
  }
  if (state_ != 1 || inspect_) {
    if (state_ != 1) state_ = 2;
    worker_->PostTask(FROM_HERE, base::BindOnce(&DeletePartialDirectory, directory_));
  }
}
void VideoStream::Inspect(GURL manifest, Reply reply, bool dash) {
  inspect_ = true; dash_ = dash;
  base::SequencedTaskRunner::GetCurrentDefault()->PostDelayedTask(FROM_HERE,
      base::BindOnce([](base::WeakPtr<VideoStream> job) {
        if (job && job->state_ == 0) job->Fail("스트림 확인 시간이 초과되었습니다. 원본 탭을 확인하고 다시 시도해 주세요.");
      }, weak_factory_.GetWeakPtr()), base::Seconds(30));
  worker_->PostTaskAndReplyWithResult(FROM_HERE,
      base::BindOnce(&Directory, directory_), base::BindOnce(&VideoStream::DirectoryReady,
      weak_factory_.GetWeakPtr(), true, std::move(manifest), std::move(reply)));
}
void VideoStream::Start(std::vector<GURL> parts, Reply reply, std::vector<GURL> audio_parts, bool transport_stream) {
  transport_stream_ = transport_stream;
  parts_ = std::move(parts);
  audio_start_ = parts_.size();
  for (auto& url : audio_parts) parts_.push_back(std::move(url));
  worker_->PostTaskAndReplyWithResult(FROM_HERE,
      base::BindOnce(&Directory, directory_), base::BindOnce(&VideoStream::DirectoryReady,
      weak_factory_.GetWeakPtr(), false, GURL(), std::move(reply)));
}
void VideoStream::DirectoryReady(bool inspect, GURL manifest, Reply reply, bool created) {
  reply_ = std::move(reply);
  if (!created) { Fail("영상 저장 폴더를 만들지 못했습니다."); return; }
  if (state_ != 0) { Fail("영상 저장이 취소되었습니다."); return; }
  if (inspect) Fetch(manifest, directory_.AppendASCII(dash_ ? "manifest.mpd" : "manifest.m3u8"));
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
  if (item->IsDangerous() || item->IsInsecure()) {
    Fail("브라우저의 안전 검사로 영상 저장을 중단했습니다."); return;
  }
  if (item->GetReceivedBytes() > (inspect_ ? 2LL * 1024 * 1024 : transport_stream_ ? 8LL * 1024 * 1024 : 8LL * 1024 * 1024 * 1024) ||
      received_ + item->GetReceivedBytes() > 8.0 * 1024 * 1024 * 1024) {
    Fail(inspect_ ? "재생 목록이 2 MB 제한을 초과했습니다." : transport_stream_ ? "MPEG-TS 구간이 현재 변환 제한인 8 MB를 초과했습니다." : "영상·음성의 합계가 현재 저장 제한인 8 GB를 초과했습니다."); return;
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
    switch (item->GetLastReason()) {
      case download::DOWNLOAD_INTERRUPT_REASON_FILE_NAME_TOO_LONG:
        Fail("영상 저장 경로가 너무 깁니다. 더 짧은 경로의 브라우저 프로필에서 다시 시도해 주세요."); return;
      case download::DOWNLOAD_INTERRUPT_REASON_FILE_NO_SPACE:
        error_ = "저장 공간이 부족합니다. 공간을 확보한 뒤 재개해 주세요."; break;
      case download::DOWNLOAD_INTERRUPT_REASON_FILE_ACCESS_DENIED:
        error_ = "영상 저장 폴더에 접근할 수 없습니다. 폴더 권한을 확인한 뒤 재개해 주세요."; break;
      default:
        error_ = "영상 구간 다운로드가 중단되었습니다. 연결 상태와 저장 폴더를 확인한 뒤 재개해 주세요.";
    }
    paused_ = true;
  }
}
void VideoStream::OnDownloadDestroyed(download::DownloadItem* item) {
  observation_.Reset(); Fail("영상 다운로드가 종료되었습니다.");
}
void VideoStream::PartReady(base::FilePath path, GURL final_url) {
  if (state_ != 0) { waiting_ = false; if (state_ != 1) Cleanup(); return; }
  if (path.DirName() != directory_) { waiting_ = false; Fail("영상 구간 저장 경로가 일치하지 않습니다."); return; }
  if (inspect_) {
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce([](base::FilePath path) { std::string text; base::ReadFileToStringWithMaxSize(path, &text, 2 * 1024 * 1024); return text; }, path),
        base::BindOnce(&VideoStream::Inspected, weak_factory_.GetWeakPtr(), final_url));
  } else if (transport_stream_) {
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce(&ReadTransportPart, path),
        base::BindOnce(&VideoStream::TransmuxInput, weak_factory_.GetWeakPtr(), path));
  } else {
    worker_->PostTaskAndReplyWithResult(FROM_HERE,
        base::BindOnce(&AppendPart, path, directory_.AppendASCII(completed_ >= audio_start_ ? "audio.part" : "video.part"), completed_ == 0 || completed_ == audio_start_),
        base::BindOnce(&VideoStream::Appended, weak_factory_.GetWeakPtr()));
  }
}
void VideoStream::TransmuxInput(base::FilePath path, std::string encoded) {
  if (state_ != 0) { waiting_ = false; if (state_ != 1) Cleanup(); return; }
  auto* source = document_.AsRenderFrameHostIfValid();
  if (encoded.empty() || !source || !source->IsActive() || !source->IsRenderFrameLive() ||
      source->GetLastCommittedURL().GetWithoutRef() != source_url_) {
    waiting_ = false; Fail("영상 구간을 변환하지 못했습니다. 원본 탭과 구간 크기(8 MB 이하)를 확인해 주세요."); return;
  }
  const auto generation = ++transmux_generation_;
  base::SequencedTaskRunner::GetCurrentDefault()->PostDelayedTask(FROM_HERE,
      base::BindOnce([](base::WeakPtr<VideoStream> job, size_t generation) {
        if (!job || job->transmux_generation_ != generation) return;
        job->waiting_ = false;
        if (job->state_ == 0) job->Fail("영상 구간 변환 시간이 초과되었습니다. 원본 탭을 새로고침한 뒤 다시 시도해 주세요.");
        else job->Cleanup();
      }, weak_factory_.GetWeakPtr(), generation), base::Seconds(30));
  if (!processor_) {
    pending_transmux_path_ = path; pending_transmux_data_ = std::move(encoded);
    content::WebContents::CreateParams params(profile_);
    params.initially_hidden = true; params.is_never_composited = true;
    processor_ = content::WebContents::Create(params); Observe(processor_.get());
    processor_->GetController().LoadURL(GURL(kProcessorUrl), content::Referrer(), ui::PAGE_TRANSITION_AUTO_TOPLEVEL, std::string());
    return;
  }
  auto* frame = processor_->GetPrimaryMainFrame();
  if (!frame || !frame->IsActive() || !frame->IsRenderFrameLive() || frame->GetLastCommittedURL() != GURL(kProcessorUrl) ||
      frame->GetProcess() == source->GetProcess()) {
    waiting_ = false; Fail("영상 변환 작업 공간을 준비하지 못했습니다."); return;
  }
  processor_isolated_ = true;
  base::DictValue request; request.Set("id", id_); request.Set("data", std::move(encoded));
  request.Set("first", completed_ == 0); request.Set("last", completed_ + 1 == parts_.size());
  std::string json; base::JSONWriter::Write(request, &json);
  const std::string script = "(() => {const request=" + json + "; const create=" +
      (completed_ == 0 ? std::string(kTransmuxerFactoryJs) : "null") + ";\n" + kVideoTransmuxerJs + "\n})()";
  frame->ExecuteJavaScriptInIsolatedWorld(base::UTF8ToUTF16(script),
      base::BindOnce(&VideoStream::Transmuxed, weak_factory_.GetWeakPtr(), path), ISOLATED_WORLD_ID_CHROME_INTERNAL);
}
void VideoStream::DOMContentLoaded(content::RenderFrameHost* frame) {
  if (!processor_ || frame != processor_->GetPrimaryMainFrame() || frame->GetLastCommittedURL() != GURL(kProcessorUrl) || pending_transmux_path_.empty()) return;
  auto path = std::move(pending_transmux_path_); pending_transmux_path_.clear();
  auto data = std::move(pending_transmux_data_);
  // Allow the observer notification to unwind before a failure can destroy
  // this private WebContents.
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
      base::BindOnce(&VideoStream::TransmuxInput, weak_factory_.GetWeakPtr(), path, std::move(data)));
}
void VideoStream::ReleaseProcessor() {
  Observe(nullptr); processor_.reset(); pending_transmux_path_.clear(); pending_transmux_data_.clear();
}
void VideoStream::Transmuxed(base::FilePath path, base::Value result) {
  ++transmux_generation_;
  if (state_ != 0) { waiting_ = false; if (state_ != 1) Cleanup(); return; }
  const auto* data = result.GetIfDict();
  const auto* encoded = data ? data->FindString("data") : nullptr;
  if (!data || !data->FindBool("ok").value_or(false) || !encoded || encoded->size() > 24 * 1024 * 1024) {
    waiting_ = false; Fail("이 MPEG-TS 구간의 코덱 또는 형식을 MP4로 변환할 수 없습니다."); return;
  }
  worker_->PostTaskAndReplyWithResult(FROM_HERE, base::BindOnce(&SaveTransmuxed, path,
      directory_.AppendASCII("video.part"), completed_ == 0, *encoded),
      base::BindOnce(&VideoStream::Appended, weak_factory_.GetWeakPtr()));
}
void VideoStream::Inspected(GURL final_url, std::string body) {
  waiting_ = false;
  if (state_ != 0) { if (state_ != 1) Cleanup(); return; }
  if (!base::IsStringUTF8(body)) { Fail("올바른 UTF-8 스트림 재생 목록이 아닙니다."); return; }
  if (dash_) {
    if (body.find("<!DOCTYPE") != std::string::npos || body.find("<!ENTITY") != std::string::npos) {
      Fail("외부 문서나 엔터티 선언이 있는 DASH 재생 목록은 지원하지 않습니다."); return;
    }
    waiting_ = true;
    data_decoder::DataDecoder::ParseXmlIsolated(body, data_decoder::mojom::XmlParser::WhitespaceBehavior::kIgnore,
        base::BindOnce([](base::WeakPtr<VideoStream> job, GURL manifest, data_decoder::DataDecoder::ValueOrError decoded) {
          if (!job || job->state_ != 0) return;
          job->waiting_ = false;
          if (!decoded.has_value()) { job->Fail("DASH 재생 목록을 읽지 못했습니다."); return; }
          job->FinishInspection(ParseVideoDash(decoded.value(), manifest));
        }, weak_factory_.GetWeakPtr(), final_url));
    return;
  }
  auto playlist = ParseVideoPlaylist(body);
  if (!playlist.error.empty()) { Fail(playlist.error.c_str()); return; }
  base::DictValue result; base::ListValue variants, parts;
  for (const auto& item : playlist.variants) {
    base::DictValue row; row.Set("url", final_url.Resolve(item.address).spec()); row.Set("quality", item.quality); variants.Append(std::move(row));
  }
  result.Set("transportStream", playlist.variants.empty() && playlist.extension == ".ts");
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
  FinishInspection(std::move(result));
}
void VideoStream::FinishInspection(base::DictValue result) {
  if (const auto* error = result.FindString("error")) { Fail(error->c_str()); return; }
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
        base::BindOnce(&Finalize, directory_, title_, page_, audio_start_ < parts_.size()), base::BindOnce(&VideoStream::Finalized, weak_factory_.GetWeakPtr()));
  } else if (!paused_) NextPart();
}
void VideoStream::NextPart() {
  if (state_ != 0 || paused_ || waiting_ || observation_.IsObserving()) return;
  if (completed_ >= parts_.size()) { Fail("영상 구간 정보가 없습니다."); return; }
  // The job directory already provides unguessable isolation. Short, distinct
  // attempt names leave room for Chromium's .crdownload suffix on Windows and
  // prevent a retry from colliding with a prior download's pending cleanup.
  Fetch(parts_[completed_], directory_.AppendASCII("p" + std::to_string(++part_attempt_) + ".mp4"));
}
void VideoStream::Finalized(bool success) {
  waiting_ = false;
  if (state_ != 0) { Cleanup(); return; }
  if (!success) { Fail("완성된 영상을 서재에 등록하지 못했습니다."); return; }
  state_ = 1; paused_ = false;
  ReleaseProcessor();
}
base::DictValue VideoStream::Status() const {
  auto result = base::DictValue(); result.Set("guid", id_); result.Set("name", title_);
  result.Set("inspection", inspect_);
  result.Set("isolatedProcessor", processor_isolated_);
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
  ReleaseProcessor();
  if (observation_.IsObserving()) { auto* item = observation_.GetSource(); observation_.Reset(); ForgetDownload(profile_, item, true); }
  if (reply_) { base::DictValue result; result.Set("error", error_); std::move(reply_).Run(std::move(result)); }
  if (!waiting_) Cleanup();
}
void VideoStream::Cleanup() {
  if (directory_.empty()) return;
  ReleaseProcessor();
  auto directory = directory_;
  // Queue behind any UI-thread download cancellation/removal, then serialize
  // deletion behind this job's outstanding file operations.
  base::SequencedTaskRunner::GetCurrentDefault()->PostTask(FROM_HERE,
      base::BindOnce([](scoped_refptr<base::SequencedTaskRunner> worker, base::FilePath directory) {
        worker->PostTask(FROM_HERE,
            base::BindOnce(&DeletePartialDirectory, directory));
      }, worker_, directory));
}
}
