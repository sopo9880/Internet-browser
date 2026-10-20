#include "chrome/browser/internet_browser/internet_browser_ui.h"

#include <memory>
#include <string>

#include "base/functional/bind.h"
#include "base/memory/ref_counted_memory.h"
#include "base/task/thread_pool.h"
#include "base/memory/weak_ptr.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/transport.h"
#include "chrome/browser/profiles/profile.h"
#include "content/public/browser/web_ui.h"
#include "content/public/browser/web_ui_data_source.h"
#include "content/public/browser/web_ui_message_handler.h"

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
