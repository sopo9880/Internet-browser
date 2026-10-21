#include "chrome/browser/internet_browser/internet_browser_ui.h"

#include <memory>
#include <set>
#include <string>
#include <vector>

#include "base/functional/bind.h"
#include "base/scoped_observation.h"
#include "base/memory/ref_counted_memory.h"
#include "base/task/thread_pool.h"
#include "base/memory/weak_ptr.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/legacy_data.h"
#include "chrome/browser/internet_browser/video_player.h"
#include "chrome/browser/internet_browser/video_downloads.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/browser/internet_browser/transport.h"
#include "chrome/browser/internet_browser/updater.h"
#include "chrome/browser/bookmarks/bookmark_model_factory.h"
#include "chrome/browser/profiles/profile.h"
#include "components/bookmarks/browser/bookmark_model.h"
#include "components/bookmarks/browser/bookmark_node.h"
#include "base/strings/utf_string_conversions.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/download_manager.h"
#include "content/public/browser/web_ui_data_source.h"
#include "content/public/browser/web_ui_message_handler.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/web_contents.h"
#include "content/public/common/referrer.h"
#include "ui/base/page_transition_types.h"
#include "url/gurl.h"

namespace {
class InternetBrowserHandler : public content::WebUIMessageHandler,
                               public content::DownloadManager::Observer {
 public:
  void RegisterMessages() override {
    web_ui()->RegisterMessageCallback("internetBrowserUpdate",
        base::BindRepeating(&InternetBrowserHandler::Update, base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserStatus",
        base::BindRepeating(&InternetBrowserHandler::Status,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserSave",
        base::BindRepeating(&InternetBrowserHandler::Save,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserLegacy",
        base::BindRepeating(&InternetBrowserHandler::Legacy,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserRenameVideo",
        base::BindRepeating(&InternetBrowserHandler::RenameVideo, base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserVideos",
        base::BindRepeating(&InternetBrowserHandler::Videos,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserImportBookmarks",
        base::BindRepeating(&InternetBrowserHandler::ImportBookmarks,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserOpenVideo",
        base::BindRepeating(&InternetBrowserHandler::OpenVideo,
                             base::Unretained(this)));
  }
  void OnJavascriptDisallowed() override {
    weak_factory_.InvalidateWeakPtrs();
    updater_.reset();
    download_observation_.Reset();
    pending_libraries_.clear();
  }
  void OnManagerInitialized() override {
    download_observation_.Reset();
    auto pending = std::move(pending_libraries_);
    pending_libraries_.clear();
    for (const auto& id : pending) VideosReady(id);
  }
  void ManagerGoingDown(content::DownloadManager* manager) override {
    download_observation_.Reset();
    auto pending = std::move(pending_libraries_);
    pending_libraries_.clear();
    for (const auto& id : pending) {
      base::DictValue result; result.Set("videos", base::ListValue());
      result.Set("error", "다운로드 기록을 불러오지 못했습니다.");
      Reply(id, std::move(result));
    }
  }
 private:
  void Reply(const std::string& id, base::DictValue data) {
    if (IsJavascriptAllowed())
      ResolveJavascriptCallback(base::Value(id), data);
  }
  void Update(const base::ListValue& args) {
    if (args.size() != 2 || !args[0].is_string() || !args[1].is_string()) return;
    AllowJavascript();
    if (!updater_) updater_ = std::make_unique<internet_browser::NativeUpdater>(Profile::FromWebUI(web_ui()));
    auto reply = base::BindOnce(&InternetBrowserHandler::Reply, weak_factory_.GetWeakPtr(), args[0].GetString());
    const auto& command = args[1].GetString();
    if (command == "check") updater_->Check(std::move(reply));
    else if (command == "download") updater_->Download(std::move(reply));
    else if (command == "install") updater_->OpenVerifiedInstaller(std::move(reply));
    else if (command == "settings") {
      base::DictValue result;result.Set("opened", updater_->OpenInstallSettings());std::move(reply).Run(std::move(result));
    } else {
      base::DictValue result;result.Set("error", "알 수 없는 업데이트 요청입니다.");std::move(reply).Run(std::move(result));
    }
  }
  void Status(const base::ListValue& args) {
    if (args.size() != 1 || !args[0].is_string())
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&internet_browser::GetStatus),
        base::BindOnce(&InternetBrowserHandler::Reply,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void Save(const base::ListValue& args) {
    if ((args.size() != 3 && args.size() != 4) || !args[0].is_string() || !args[1].is_bool() ||
        !args[2].is_string() || (args.size() == 4 && !args[3].is_dict()))
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce([](bool enabled, std::string preset, base::DictValue custom) {
          base::DictValue result;
          result.Set("saved", internet_browser::SaveConfiguration(enabled, preset, std::move(custom)));
          return result;
        }, args[1].GetBool(), args[2].GetString(),
           args.size() == 4 ? args[3].GetDict().Clone() : base::DictValue()),
        base::BindOnce(&InternetBrowserHandler::Reply,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void Legacy(const base::ListValue& args) {
    if (args.size() != 1 || !args[0].is_string())
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&internet_browser::ReadLegacyData),
        base::BindOnce(&InternetBrowserHandler::Reply,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void Videos(const base::ListValue& args) {
    if (args.size() != 1 || !args[0].is_string())
      return;
    AllowJavascript();
    auto* manager = Profile::FromWebUI(web_ui())->GetDownloadManager();
    if (!manager->IsManagerInitialized()) {
      pending_libraries_.push_back(args[0].GetString());
      if (!download_observation_.IsObserving()) download_observation_.Observe(manager);
      return;
    }
    VideosReady(args[0].GetString());
  }
  void VideosReady(const std::string& id) {
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&internet_browser::ReadVideoLibraryWithDownloads, VideoStateFile(),
                       internet_browser::CollectVideoDownloads(Profile::FromWebUI(web_ui())),
                       Profile::FromWebUI(web_ui())->IsOffTheRecord()),
        base::BindOnce(&InternetBrowserHandler::Reply,
                        weak_factory_.GetWeakPtr(), id));
  }
  void RenameVideo(const base::ListValue& args) {
    if (args.size() != 3 || !args[0].is_string() || !args[1].is_string() || !args[2].is_string()) return;
    AllowJavascript();
    if (Profile::FromWebUI(web_ui())->IsOffTheRecord()) {
      base::DictValue result; result.Set("saved", false);
      result.Set("error", "시크릿 창에서는 영상 제목을 저장하지 않습니다.");
      Reply(args[0].GetString(), std::move(result));
      return;
    }
    base::ThreadPool::PostTaskAndReplyWithResult(FROM_HERE, {base::MayBlock()},
        base::BindOnce([](base::FilePath state, std::string requested, std::string title,
                           std::vector<internet_browser::CompletedVideoDownload> downloads) {
          auto library = internet_browser::ReadVideoLibraryWithDownloads(state, std::move(downloads));
          base::DictValue result;
          if (const auto* videos = library.FindList("videos")) {
            for (const auto& video : *videos) {
              const auto& item = video.GetDict();
              const auto* url = item.FindString("url");
              const auto* name = item.FindString("name");
              if (url && name && *url == requested) {
                result.Set("saved", internet_browser::SaveVideoTitle(state, *name, title));
                result.Set("title", internet_browser::NormalizeVideoTitle(title));
                return result;
              }
            }
          }
          result.Set("saved", false);
          return result;
        }, VideoStateFile(), args[1].GetString(), args[2].GetString(),
           internet_browser::CollectVideoDownloads(Profile::FromWebUI(web_ui()))),
        base::BindOnce(&InternetBrowserHandler::Reply, weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void ImportBookmarks(const base::ListValue& args) {
    if (args.size() != 1 || !args[0].is_string())
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&internet_browser::ReadLegacyData),
        base::BindOnce(&InternetBrowserHandler::CompleteImport,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void CompleteImport(const std::string& id, base::DictValue legacy) {
    if (!IsJavascriptAllowed())
      return;
    auto* model = BookmarkModelFactory::GetForBrowserContext(Profile::FromWebUI(web_ui()));
    base::DictValue result;
    if (!model || !model->loaded()) {
      result.Set("error", "북마크를 불러오는 중입니다. 잠시 후 다시 시도하세요.");
      Reply(id, std::move(result));
      return;
    }
    const auto* urls = legacy.FindList("bookmarks");
    int imported = 0;
    if (urls && !urls->empty()) {
      const bookmarks::BookmarkNode* folder = nullptr;
      for (const auto& child : model->bookmark_bar_node()->children()) {
        std::string marker;
        if (child->is_folder() &&
            child->GetMetaInfo("internet_browser_legacy", &marker) && marker == "flutter") {
          folder = child.get();
          break;
        }
      }
      if (!folder) {
        bookmarks::BookmarkNode::MetaInfoMap metadata;
        metadata["internet_browser_legacy"] = "flutter";
        folder = model->AddFolder(model->bookmark_bar_node(),
            model->bookmark_bar_node()->children().size(),
            u"이전 Internet Browser", &metadata);
      }
      std::set<std::string> existing;
      for (const auto& child : folder->children())
        if (child->is_url())
          existing.insert(child->url().spec());
      for (const auto& entry : *urls) {
        GURL url(entry.GetString());
        if (url.is_valid() && url.SchemeIsHTTPOrHTTPS() &&
            existing.insert(url.spec()).second) {
          model->AddURL(folder, folder->children().size(),
                        base::UTF8ToUTF16(url.spec()), url);
          ++imported;
        }
      }
    }
    result.Set("imported", imported);
    Reply(id, std::move(result));
  }
  base::FilePath VideoStateFile() {
    auto* profile = Profile::FromWebUI(web_ui());
    return profile->GetOriginalProfile()->GetPath().AppendASCII("internet-browser-video-state.json");
  }
  void OpenVideo(const base::ListValue& args) {
    if (args.size() != 2 || !args[0].is_string() || !args[1].is_string())
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce([](const std::string& requested, const base::FilePath& state_file,
                           std::vector<internet_browser::CompletedVideoDownload> downloads, bool private_session) {
          base::DictValue result;
          auto library = internet_browser::ReadVideoLibraryWithDownloads(state_file, std::move(downloads), private_session);
          if (const auto* videos = library.FindList("videos")) {
            for (const auto& video : *videos) {
              const auto* url = video.GetDict().FindString("url");
              if (url && *url == requested) {
                library.Set("selected", *url);
                return library;
              }
            }
          }
          return result;
        }, args[1].GetString(), VideoStateFile(),
           internet_browser::CollectVideoDownloads(Profile::FromWebUI(web_ui())),
           Profile::FromWebUI(web_ui())->IsOffTheRecord()),
        base::BindOnce(&InternetBrowserHandler::CompleteOpenVideo,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
  }
  void CompleteOpenVideo(const std::string& id, base::DictValue video) {
    if (!IsJavascriptAllowed())
      return;
    const auto* selected = video.FindString("selected");
    const std::string url = selected ? *selected : std::string();
    const bool installed = selected && internet_browser::InstallVideoPlayer(
        web_ui()->GetWebContents(), std::move(video), url,
        Profile::FromWebUI(web_ui())->IsOffTheRecord() ? base::FilePath() : VideoStateFile());
    base::DictValue result;
    result.Set("opened", installed);
    Reply(id, std::move(result));
    if (installed) {
      // Browser-initiated navigation permits a trusted local media document;
      // arbitrary renderer-supplied file paths never pass the library lookup.
      web_ui()->GetWebContents()->GetController().LoadURL(
          GURL(url), content::Referrer(), ui::PAGE_TRANSITION_LINK, std::string());
    }
  }
  base::ScopedObservation<content::DownloadManager, content::DownloadManager::Observer> download_observation_{this};
  std::vector<std::string> pending_libraries_;
  std::unique_ptr<internet_browser::NativeUpdater> updater_;
  base::WeakPtrFactory<InternetBrowserHandler> weak_factory_{this};
};
}  // namespace

InternetBrowserUI::InternetBrowserUI(content::WebUI* web_ui)
    : content::WebUIController(web_ui) {
  auto* profile = Profile::FromWebUI(web_ui);
  auto* source = content::WebUIDataSource::CreateAndAdd(profile, "internet-browser");
  source->SetRequestFilter(
      base::BindRepeating([](const std::string&) { return true; }),
      base::BindRepeating([](const std::string& path,
                            content::WebUIDataSource::GotDataCallback callback) {
        std::string data;
        if (path.empty() || path == "index.html")
          data = internet_browser::kIndexHtml;
        else if (path == "app.js")
          data = internet_browser::kAppJs;
        else if (path == "style.css")
          data = internet_browser::kStyleCss;
        else if (path == "logo.svg")
          data = internet_browser::kLogoSvg;
        else if (path == "licenses.html")
          data = internet_browser::kLicensesHtml;
        std::move(callback).Run(base::MakeRefCounted<base::RefCountedString>(std::move(data)));
      }));
  web_ui->AddMessageHandler(std::make_unique<InternetBrowserHandler>());
}
InternetBrowserUI::~InternetBrowserUI() = default;
