#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_DASH_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_DASH_H_
#include "base/values.h"
#include "url/gurl.h"
namespace internet_browser {
// Consumes only the value tree returned by the isolated XML decoder. URLs are
// resolved but fetched later through the originating frame's download manager.
base::DictValue ParseVideoDash(const base::Value& root, const GURL& manifest);
}
#endif
