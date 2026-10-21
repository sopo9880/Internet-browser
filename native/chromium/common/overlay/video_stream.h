#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_STREAM_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_STREAM_H_
#include <memory>
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
#include "url/gurl.h"
class Profile;
namespace internet_browser {
// Each manifest/part uses the ordinary frame-bound download path with safety
// checks required. A partial output is never exposed in the offline library.
class VideoStream : public download::DownloadItem::Observer {
 public:
  using Reply = base::OnceCallback<void(base::DictValue)>;
  VideoStream(Profile* profile, content::WeakDocumentPtr document, std::string title, std::string page);
  ~VideoStream() override;
  void Inspect(GURL manifest, Reply reply, bool dash = false);
  void Start(std::vector<GURL> parts, Reply reply, std::vector<GURL> audio_parts = {});
  base::DictValue Status() const;
  bool Control(const std::string& action);
  void OnDownloadUpdated(download::DownloadItem* item) override;
  void OnDownloadDestroyed(download::DownloadItem* item) override;
 private:
  void DirectoryReady(bool inspect, GURL manifest, Reply reply, bool created);
  void NextPart();
  void Fetch(const GURL& url, const base::FilePath& target);
  void Started(download::DownloadItem* item, download::DownloadInterruptReason reason);
  void PartReady(base::FilePath path, GURL final_url);
  void Appended(bool success);
  void Inspected(GURL final_url, std::string body);
  void FinishInspection(base::DictValue result);
  void Finalized(bool success);
  void Fail(const char* error);
  void Cleanup();
  raw_ptr<Profile> profile_;
  content::WeakDocumentPtr document_;
  GURL source_url_;
  std::string title_, page_, id_, error_;
  base::FilePath directory_;
  std::vector<GURL> parts_;
  size_t completed_ = 0;
  size_t audio_start_ = 0;
  double received_ = 0;
  int state_ = 0;
  bool inspect_ = false, dash_ = false, paused_ = false, waiting_ = false;
  Reply reply_;
  scoped_refptr<base::SequencedTaskRunner> worker_;
  base::ScopedObservation<download::DownloadItem, download::DownloadItem::Observer> observation_{this};
  base::WeakPtrFactory<VideoStream> weak_factory_{this};
};
}
#endif
