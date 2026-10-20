#include "chrome/browser/internet_browser/video_player.h"

#include <algorithm>
#include <memory>
#include <optional>
#include <string>
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/strings/utf_string_conversions.h"
#include "base/supports_user_data.h"
#include "base/task/sequenced_task_runner.h"
#include "base/task/thread_pool.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/video_metadata.h"
#include "chrome/common/chrome_isolated_world_ids.h"
#include "content/public/browser/navigation_controller.h"
#include "content/public/browser/navigation_handle.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/browser/web_contents.h"
#include "content/public/browser/web_contents_observer.h"
#include "content/public/common/referrer.h"
#include "ui/base/page_transition_types.h"
#include "url/gurl.h"

namespace internet_browser {
namespace {
const char kVideoPlayerKey[] = "internet_browser_video_player";
constexpr char kCommandPrefix[] = "INTERNET_BROWSER_LOCAL_PLAYER:";
class VideoPlayer : public base::SupportsUserData::Data,
                    public content::WebContentsObserver {
 public:
  VideoPlayer(content::WebContents* contents, base::ListValue videos, size_t index,
              const base::FilePath& file)
      : content::WebContentsObserver(contents), videos_(std::move(videos)), index_(index),
        state_file_(file), writer_(base::ThreadPool::CreateSequencedTaskRunner(
            {base::MayBlock(), base::TaskShutdownBehavior::BLOCK_SHUTDOWN})) {}
  void DidFinishNavigation(content::NavigationHandle* navigation) override {
    if (navigation->IsInPrimaryMainFrame() && navigation->HasCommitted() &&
        !navigation->IsSameDocument() && navigation->GetURL() != CurrentUrl())
      armed_ = false;
  }
  void DidFinishLoad(content::RenderFrameHost* frame, const GURL& url) override {
    if (!armed_ || frame != web_contents()->GetPrimaryMainFrame() || url != CurrentUrl())
      return;
    auto options = videos_[index_].GetDict().Clone();
    options.Merge(player_options_.Clone());
    options.Set("hasPrevious", index_ > 0);
    options.Set("hasNext", index_ + 1 < videos_.size());
    std::string json;
    if (!base::JSONWriter::Write(options, &json))
      return;
    std::string script = "(() => { const options = " + json + ";\n" + kVideoPlayerJs + "\n})()";
    frame->ExecuteJavaScriptInIsolatedWorld(base::UTF8ToUTF16(script), {},
                                           ISOLATED_WORLD_ID_CHROME_INTERNAL);
  }
  void OnDidAddMessageToConsole(content::RenderFrameHost* frame,
      blink::mojom::ConsoleMessageLevel level, const std::u16string& message,
      int32_t line, const std::u16string& source,
      const std::optional<std::u16string>& stack) override {
    if (!armed_ || frame != web_contents()->GetPrimaryMainFrame() ||
        frame->GetLastCommittedURL() != CurrentUrl() || message.size() > 1024)
      return;
    std::string text = base::UTF16ToUTF8(message);
    if (!text.starts_with(kCommandPrefix))
      return;
    auto command = base::JSONReader::ReadDict(text.substr(sizeof(kCommandPrefix) - 1),
                                             base::JSON_PARSE_RFC);
    if (!command)
      return;
    const auto* action = command->FindString("action");
    if (!action)
      return;
    if (*action == "next" || *action == "previous") {
      const double rate = command->FindDouble("rate").value_or(1);
      const double volume = command->FindDouble("volume").value_or(1);
      if (std::isfinite(rate) && rate >= 0.25 && rate <= 2)
        player_options_.Set("rate", rate);
      if (std::isfinite(volume) && volume >= 0 && volume <= 1)
        player_options_.Set("volume", volume);
      const auto* fit = command->FindString("fit");
      player_options_.Set("fit", fit && *fit == "cover" ? "cover" : "contain");
      player_options_.Set("loop", command->FindBool("loop").value_or(false));
    }
    if (*action == "position") {
      const double position = command->FindDouble("positionMs").value_or(-1);
      const double duration = command->FindDouble("durationMs").value_or(-1);
      if (!std::isfinite(position) || !std::isfinite(duration) || position < 0 ||
          duration < 0 || position > 604800000 || duration > 604800000)
        return;
      auto& item = videos_[index_].GetDict();
      item.Set("lastPositionMs", position);
      const auto* name = item.FindString("name");
      if (name)
        writer_->PostTask(FROM_HERE, base::BindOnce([](base::FilePath file,
            std::string name, double position, double duration) {
          SaveVideoPosition(file, name, position, duration);
        }, state_file_, *name, position, duration));
    } else if (*action == "next" && index_ + 1 < videos_.size()) {
      ++index_;
      Navigate();
    } else if (*action == "previous" && index_ > 0) {
      --index_;
      Navigate();
    }
  }
 private:
  GURL CurrentUrl() const { return GURL(*videos_[index_].GetDict().FindString("url")); }
  void Navigate() {
    web_contents()->GetController().LoadURL(CurrentUrl(), content::Referrer(),
                                            ui::PAGE_TRANSITION_LINK, std::string());
  }
  base::DictValue player_options_;
  base::ListValue videos_;
  size_t index_;
  base::FilePath state_file_;
  scoped_refptr<base::SequencedTaskRunner> writer_;
  bool armed_ = true;
};
}  // namespace
bool InstallVideoPlayer(content::WebContents* contents, base::DictValue library,
                        const std::string& selected, const base::FilePath& state_file) {
  auto* videos = library.FindList("videos");
  if (!videos || videos->empty())
    return false;
  size_t selected_index = videos->size();
  for (size_t i = 0; i < videos->size(); ++i) {
    const auto* item = (*videos)[i].GetIfDict();
    if (!item || !item->FindString("name") || !item->FindString("url") ||
        !GURL(*item->FindString("url")).SchemeIsFile())
      return false;
    if (*item->FindString("url") == selected)
      selected_index = i;
  }
  if (selected_index == videos->size())
    return false;
  contents->SetUserData(kVideoPlayerKey, std::make_unique<VideoPlayer>(
      contents, videos->Clone(), selected_index, state_file));
  return true;
}
}  // namespace internet_browser
