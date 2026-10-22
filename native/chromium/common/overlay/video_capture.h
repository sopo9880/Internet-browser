#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_CAPTURE_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_CAPTURE_H_
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/supports_user_data.h"
#include "base/scoped_observation.h"
#include "chrome/browser/profiles/profile_observer.h"
#include "base/values.h"
#include "content/public/browser/weak_document_ptr.h"
#include "url/gurl.h"
class Profile;
namespace internet_browser {
class VideoStream;
class YoutubeVideo;
// UI-thread, profile-bound discovery. Renderer-supplied addresses are untrusted;
// downloads retain their source frame and Chromium's ordinary security checks.
class VideoCapture : public base::SupportsUserData::Data, public ProfileObserver {
 public:
  using Reply = base::OnceCallback<void(base::DictValue)>;
  explicit VideoCapture(Profile* profile);
  ~VideoCapture() override;
  static VideoCapture* Get(Profile* profile);
  void Scan(Reply reply);
  void Inspect(const std::string& token, Reply reply);
  void Download(const std::string& token, Reply reply);
  base::DictValue Transfers();
  base::DictValue Control(const std::string& guid, const std::string& action);
  void OnProfileWillBeDestroyed(Profile*) override;
 private:
  struct Candidate {
    content::WeakDocumentPtr document;
    GURL source_url;
    base::DictValue data;
    std::vector<GURL> parts;
    std::vector<GURL> audio_parts;
    bool transport_stream = false;
  };
  void Inspected(std::string token, Reply reply, base::DictValue result);
  void Scanned(content::WeakDocumentPtr document, base::Value value);
  void FinishScan();
  raw_ptr<Profile> profile_;
  std::map<std::string, Candidate> candidates_;
  std::vector<std::unique_ptr<VideoStream>> streams_;
  std::vector<std::unique_ptr<YoutubeVideo>> youtube_;
  base::ListValue found_;
  std::set<std::string> reasons_;
  Reply scan_reply_;
  base::ScopedObservation<Profile, ProfileObserver> profile_observation_{this};
  size_t pending_ = 0;
  base::WeakPtrFactory<VideoCapture> scan_factory_{this};
  base::WeakPtrFactory<VideoCapture> weak_factory_{this};
};
}
#endif
