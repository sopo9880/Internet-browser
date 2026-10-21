#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_SUBTITLES_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_SUBTITLES_H_
#include "base/values.h"
namespace internet_browser {
// Worker-only: reads a bounded local sidecar for the browser-approved video.
base::DictValue LoadVideoSubtitles(base::DictValue options);
}
#endif
