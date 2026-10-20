#ifndef CHROME_BROWSER_INTERNET_BROWSER_UPDATE_MANIFEST_H_
#define CHROME_BROWSER_INTERNET_BROWSER_UPDATE_MANIFEST_H_
#include <optional>
#include <string>
#include "base/strings/string_util.h"
#include "base/values.h"
#include "chrome/browser/internet_browser/update_validation.h"
#include "url/gurl.h"

namespace internet_browser {
inline base::DictValue ParseUpdateManifest(const base::DictValue& release,
                                           const std::string& installed,
                                           bool android) {
  base::DictValue result;
  result.Set("available", false);
  result.Set("canInstall", false);
  const auto* tag = release.FindString("tag_name");
  auto current = UpdateVersion(installed);
  auto latest = tag ? UpdateVersion(*tag) : std::nullopt;
  if (!current || !latest || *latest <= *current ||
      release.FindBool("draft").value_or(true) ||
      release.FindBool("prerelease").value_or(true))
    return result;
  const std::string version = tag->starts_with('v') ? tag->substr(1) : *tag;
  result.Set("available", true);
  result.Set("tag", *tag);
  result.Set("version", version);
  result.Set("releasePage", "https://github.com/sopo9880/Internet-browser/releases/tag/" + *tag);
  if (const auto* description = release.FindString("body"))
    result.Set("description", description->substr(0, 65536));
  if (const auto* assets = release.FindList("assets")) {
    for (const auto& value : *assets) {
      const auto* asset = value.GetIfDict();
      if (!asset) continue;
      const auto* name = asset->FindString("name");
      const auto* state = asset->FindString("state");
      const auto* address = asset->FindString("browser_download_url");
      const auto size = asset->FindInt("size");
      const auto* digest = asset->FindString("digest");
      if (!name || !state || *state != "uploaded" || !address || !size || !digest ||
          !ValidUpdateAsset(*tag, *name, *address, *size, *digest, android))
        continue;
      base::DictValue installer;
      installer.Set("name", *name);
      installer.Set("url", *address);
      installer.Set("size", *size);
      installer.Set("sha256", base::ToLowerASCII(digest->substr(7)));
      result.Set("installer", std::move(installer));
      result.Set("canInstall", true);
      break;
    }
  }
  return result;
}
}  // namespace internet_browser
#endif
