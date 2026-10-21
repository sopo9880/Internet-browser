#ifndef CHROME_BROWSER_INTERNET_BROWSER_UPDATE_VALIDATION_H_
#define CHROME_BROWSER_INTERNET_BROWSER_UPDATE_VALIDATION_H_
#include <array>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <string_view>

namespace internet_browser {
inline constexpr int kMaxInstallerBytes = 800 * 1024 * 1024;
inline std::optional<std::array<uint32_t, 4>> UpdateVersion(std::string_view text) {
  if (text.starts_with('v')) text.remove_prefix(1);
  if (text.empty() || text.size() > 48) return std::nullopt;
  std::array<uint32_t, 4> result{};
  size_t component = 0;
  bool has_digit = false;
  for (char character : text) {
    if (character == '.') {
      if (!has_digit || ++component >= result.size()) return std::nullopt;
      has_digit = false;
    } else {
      if (character < '0' || character > '9') return std::nullopt;
      uint32_t digit = character - '0';
      if (result[component] > (std::numeric_limits<uint32_t>::max() - digit) / 10)
        return std::nullopt;
      result[component] = result[component] * 10 + digit;
      has_digit = true;
    }
  }
  if (!has_digit || component < 2) return std::nullopt;
  return result;
}
inline bool ValidUpdateAsset(std::string_view tag, std::string_view name,
                             std::string_view address, int64_t size,
                             std::string_view digest, bool android) {
  if (!UpdateVersion(tag) || size <= 0 || size > kMaxInstallerBytes) return false;
  const auto version = tag.starts_with('v') ? tag.substr(1) : tag;
  std::string expected = "Internet-browser-" + std::string(android ? "Android-v" : "Windows-Setup-v") +
      std::string(version) + (android ? ".apk" : ".exe");
  if (name.size() != expected.size()) return false;
  for (size_t i = 0; i < name.size(); ++i) {
    auto lower = [](char value) {return value >= 'A' && value <= 'Z' ? value + ('a' - 'A') : value;};
    if (lower(name[i]) != lower(expected[i])) return false;
  }
  if (address != "https://github.com/sopo9880/Internet-browser/releases/download/" +
      std::string(tag) + "/" + std::string(name)) return false;
  if (!digest.starts_with("sha256:") || digest.size() != 71) return false;
  return digest.find_first_not_of("0123456789abcdefABCDEF", 7) == std::string_view::npos;
}
}  // namespace internet_browser
#endif
