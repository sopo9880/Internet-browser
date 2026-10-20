#ifndef CHROME_BROWSER_INTERNET_BROWSER_LEGACY_DATA_H_
#define CHROME_BROWSER_INTERNET_BROWSER_LEGACY_DATA_H_

#include "base/values.h"

namespace internet_browser {
// Blocking reads, called only on a worker sequence. Original files are untouched.
base::DictValue ReadLegacyData();
base::DictValue ReadVideoLibrary();
}

#endif
