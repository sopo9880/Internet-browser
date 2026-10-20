#include "chrome/browser/internet_browser/internet_browser_ui.h"

#include <memory>
#include <set>
#include <string>

#include "base/functional/bind.h"
#include "base/memory/ref_counted_memory.h"
#include "base/task/thread_pool.h"
#include "base/memory/weak_ptr.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/legacy_data.h"
#include "chrome/browser/internet_browser/transport.h"
#include "chrome/browser/bookmarks/bookmark_model_factory.h"
#include "chrome/browser/profiles/profile.h"
#include "components/bookmarks/browser/bookmark_model.h"
#include "components/bookmarks/browser/bookmark_node.h"
#include "base/strings/utf_string_conversions.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "content/public/browser/web_ui_message_handler.h"
#include "url/gurl.h"

namespace {
class InternetBrowserHandler : public content::WebUIMessageHandler {
 public:
  void RegisterMessages() override {
    web_ui()->RegisterMessageCallback("internetBrowserStatus",
        base::BindRepeating(&InternetBrowserHandler::Status,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserSave",
        base::BindRepeating(&InternetBrowserHandler::Save,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserLegacy",
        base::BindRepeating(&InternetBrowserHandler::Legacy,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserVideos",
        base::BindRepeating(&InternetBrowserHandler::Videos,
                             base::Unretained(this)));
    web_ui()->RegisterMessageCallback("internetBrowserImportBookmarks",
        base::BindRepeating(&InternetBrowserHandler::ImportBookmarks,
                             base::Unretained(this)));
  }
  void OnJavascriptDisallowed() override {
    weak_factory_.InvalidateWeakPtrs();
  }
 private:
  void Reply(const std::string& id, base::DictValue data) {
    if (IsJavascriptAllowed())
      ResolveJavascriptCallback(base::Value(id), data);
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
    if (args.size() != 3 || !args[0].is_string() || !args[1].is_bool() ||
        !args[2].is_string())
      return;
    AllowJavascript();
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce([](bool enabled, std::string preset) {
          base::DictValue result;
          result.Set("saved", internet_browser::SaveConfiguration(enabled, preset));
          return result;
        }, args[1].GetBool(), args[2].GetString()),
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
    base::ThreadPool::PostTaskAndReplyWithResult(
        FROM_HERE, {base::MayBlock()},
        base::BindOnce(&internet_browser::ReadVideoLibrary),
        base::BindOnce(&InternetBrowserHandler::Reply,
                        weak_factory_.GetWeakPtr(), args[0].GetString()));
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
        std::move(callback).Run(base::MakeRefCounted<base::RefCountedString>(std::move(data)));
      }));
  web_ui->AddMessageHandler(std::make_unique<InternetBrowserHandler>());
}
InternetBrowserUI::~InternetBrowserUI() = default;
