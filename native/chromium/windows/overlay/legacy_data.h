#ifndef CHROME_BROWSER_INTERNET_BROWSER_LEGACY_DATA_H_
#define CHROME_BROWSER_INTERNET_BROWSER_LEGACY_DATA_H_

#include "base/values.h"
#include "base/files/file_path.h"

namespace internet_browser {
// Blocking reads, called only on a worker sequence. Original files are untouched.
base::DictValue ReadLegacyData();
base::DictValue ReadVideoLibrary(const base::FilePath& state_file = {});
}

#endif
