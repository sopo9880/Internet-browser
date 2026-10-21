#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PLAYER_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_PLAYER_H_
#include <string>
#include "base/files/file_path.h"
#include "base/values.h"
namespace content { class WebContents; }
namespace internet_browser {
// Call only with the library produced by the browser's own bounded file scan.
bool InstallVideoPlayer(content::WebContents* contents, base::DictValue library,
                        const std::string& selected, const base::FilePath& state_file);
}
#endif
