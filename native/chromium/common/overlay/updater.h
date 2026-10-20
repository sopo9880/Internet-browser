#ifndef CHROME_BROWSER_INTERNET_BROWSER_UPDATER_H_
#define CHROME_BROWSER_INTERNET_BROWSER_UPDATER_H_
#include <memory>
#include <optional>
#include <string>
#include "base/files/file_path.h"
#include "base/functional/callback.h"
#include "base/memory/raw_ptr.h"
#include "base/memory/weak_ptr.h"
#include "base/values.h"
namespace network { class SimpleURLLoader; }
class Profile;
namespace internet_browser {
class NativeUpdater {
 public:
  using Reply = base::OnceCallback<void(base::DictValue)>;
  explicit NativeUpdater(Profile* profile);
  ~NativeUpdater();
  bool OpenInstallSettings();
  void Check(Reply reply);
  void Download(Reply reply);
  void OpenVerifiedInstaller(Reply reply);
 private:
  void ManifestReceived(Reply reply, std::optional<std::string> body);
  void DownloadDirectoryReady(Reply reply, base::FilePath directory);
  void Downloaded(Reply reply, base::FilePath file);
  void Verified(Reply reply, base::FilePath file);
  bool busy_ = false;
  bool keep_installer_ = false;
  raw_ptr<Profile> profile_;
  std::unique_ptr<network::SimpleURLLoader> loader_;
  base::DictValue release_;
  base::FilePath directory_;
  base::FilePath verified_file_;
  base::WeakPtrFactory<NativeUpdater> weak_factory_{this};
};
}  // namespace internet_browser
#endif
