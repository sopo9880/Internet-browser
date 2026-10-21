#ifndef CHROME_BROWSER_INTERNET_BROWSER_LEGACY_TEST_PATHS_H_
#define CHROME_BROWSER_INTERNET_BROWSER_LEGACY_TEST_PATHS_H_
#include <string_view>
#include "base/command_line.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
namespace internet_browser {
// Explicit test-launcher options keep regression fixtures out of real user
// directories. Renderer messages cannot select any directory or file path.
inline base::FilePath NativeFixtureDirectory(std::string_view option,
                                             const base::FilePath& fallback) {
  const auto* command = base::CommandLine::ForCurrentProcess();
  if (!command->HasSwitch("test-type") || !command->HasSwitch(option)) return fallback;
  const auto requested = command->GetSwitchValuePath(option);
  if (!requested.IsAbsolute() || !base::DirectoryExists(requested) || base::IsLink(requested)) return {};
  return requested;
}
}  // namespace internet_browser
#endif
