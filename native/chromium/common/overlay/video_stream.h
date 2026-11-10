#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_STREAM_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_STREAM_H_
#include <memory>
#include <optional>
#include <string>
#include <vector>
#include "base/files/file_path.h"
#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/scoped_observation.h"
#include "base/task/sequenced_task_runner.h"
#include "base/values.h"
#include "components/download/public/common/download_item.h"
#include "content/public/browser/weak_document_ptr.h"
#include "content/public/browser/web_contents_observer.h"
#include "net/base/isolation_info.h"
#include "services/network/public/mojom/referrer_policy.mojom-shared.h"
#include "url/gurl.h"
#include "url/origin.h"
class Profile;
namespace internet_browser {
// Each manifest/part uses the ordinary frame-bound download path with safety
// checks required. A partial output is never exposed in the offline library.
// Once a save has started, leaving or closing the source page no longer stops
// it: later parts reuse the origin, cookie partition and referrer captured from
// that page. Inspection still requires the live page.
class VideoStream : public download::DownloadItem::Observer, public content::WebContentsObserver {
 public:
  using Reply = base::OnceCallback<void(base::DictValue)>;
  VideoStream(Profile* profile, content::WeakDocumentPtr document, std::string title, std::string page, std::string referrer_policy = {});
  ~VideoStream() override;
  void Inspect(GURL manifest, Reply reply, bool dash = false, GURL audio_manifest = GURL());
  void Start(std::vector<GURL> parts, Reply reply, std::vector<GURL> audio_parts = {}, bool transport_stream = false, bool audio_transport_stream = false, bool direct_file = false);
  base::DictValue Status() const;
  bool Control(const std::string& action);
  void Shutdown();
  void OnDownloadUpdated(download::DownloadItem* item) override;
  void OnDownloadDestroyed(download::DownloadItem* item) override;
  void DOMContentLoaded(content::RenderFrameHost* frame) override;
 private:
  void DirectoryReady(bool inspect, GURL manifest, Reply reply, bool created);
  void NextPart();
  void Fetch(const GURL& url, const base::FilePath& target);
  void Started(download::DownloadItem* item, download::DownloadInterruptReason reason);
  void PartReady(base::FilePath path, GURL final_url);
  void TransmuxInput(base::FilePath path, std::string encoded);
  void Transmuxed(base::FilePath path, base::Value result);
  void Appended(bool success);
  void Inspected(GURL final_url, std::string body);
  void FinishInspection(base::DictValue result);
  void Finalized(bool success);
  void Fail(const char* error);
  bool RetryInterrupted(download::DownloadItem* item);
  void Cleanup();
  void ReleaseProcessor();
  bool TransportPart() const;
  raw_ptr<Profile> profile_;
  content::WeakDocumentPtr document_;
  GURL source_url_;
  // Captured from the source document at construction.
  GURL source_page_url_;
  std::optional<url::Origin> initiator_;
  net::IsolationInfo isolation_info_;
  std::optional<network::mojom::ReferrerPolicy> header_referrer_policy_;
  size_t retries_ = 0;
  std::string title_, page_, id_, error_, referrer_policy_;
  base::FilePath directory_;
  std::vector<GURL> parts_;
  GURL audio_manifest_;
  base::ListValue inspected_video_parts_;
  bool inspecting_audio_ = false;
  bool inspected_video_transport_ = false;
  bool audio_transport_stream_ = false;
  size_t completed_ = 0;
  size_t part_attempt_ = 0;
  size_t audio_start_ = 0;
  size_t transmux_generation_ = 0;
  double received_ = 0;
  int state_ = 0;
  bool inspect_ = false, dash_ = false, transport_stream_ = false, paused_ = false, waiting_ = false;
  bool processor_isolated_ = false;
  bool shutting_down_ = false;
  bool direct_file_ = false;
  Reply reply_;
  std::unique_ptr<content::WebContents> processor_;
  base::FilePath pending_transmux_path_;
  std::string pending_transmux_data_;
  scoped_refptr<base::SequencedTaskRunner> worker_;
  base::ScopedObservation<download::DownloadItem, download::DownloadItem::Observer> observation_{this};
  base::WeakPtrFactory<VideoStream> weak_factory_{this};
};
}
#endif
