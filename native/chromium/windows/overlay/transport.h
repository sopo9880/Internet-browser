#ifndef CHROME_BROWSER_INTERNET_BROWSER_TRANSPORT_H_
#define CHROME_BROWSER_INTERNET_BROWSER_TRANSPORT_H_

#include <string>

#include "base/values.h"

namespace internet_browser {
// Called before the Chromium network context is created, and at shutdown.
void StartTransport();
void StopTransport();
base::DictValue GetStatus();
bool SaveConfiguration(bool enabled, const std::string& preset);
}  // namespace internet_browser

#endif
