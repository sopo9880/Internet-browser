#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_YOUTUBE_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_YOUTUBE_H_
#include <memory>
#include <optional>
#include <string>
#include <vector>
#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/values.h"
#include "content/public/browser/weak_document_ptr.h"
#include "url/gurl.h"
class Profile;
namespace network { class SimpleURLLoader; }
namespace internet_browser {
// Anonymous, bounded HLS discovery for the exact currently open YouTube video.
// No account cookies, signature deciphering, DRM or age-check overrides.
class YoutubeVideo {
 public:
  using Reply = base::OnceCallback<void(base::DictValue)>;
  YoutubeVideo(Profile* profile, content::WeakDocumentPtr document, GURL source);
  ~YoutubeVideo();
  static std::string VideoId(const GURL& source);
  void Discover(const std::string& visitor, const base::DictValue* size_hints, Reply reply);
  void Resolve(GURL video, GURL audio, Reply reply);
  bool done() const { return done_; }
 private:
  enum class Phase { kPlayer, kMaster, kVideo, kAudio };
  bool Current() const;
  void Fetch(GURL url, Phase phase, std::string body = {});
  void Loaded(GURL url, Phase phase, std::optional<std::string> body);
  void Finish(base::DictValue result);
  void Fail(const char* reason);
  raw_ptr<Profile> profile_;
  content::WeakDocumentPtr document_;
  GURL source_, audio_;
  std::string video_id_;
  std::vector<GURL> video_parts_;
  base::DictValue size_hints_;
  double duration_seconds_ = 0;
  bool transport_ = false, done_ = false;
  Reply reply_;
  std::unique_ptr<network::SimpleURLLoader> loader_;
  base::WeakPtrFactory<YoutubeVideo> weak_factory_{this};
};
}
#endif
