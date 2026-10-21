#ifndef CHROME_BROWSER_INTERNET_BROWSER_DPI_OPTIONS_H_
#define CHROME_BROWSER_INTERNET_BROWSER_DPI_OPTIONS_H_

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace internet_browser {
struct CustomDpiOptions {
  bool split = true;
  std::string split_value = "1+s";
  bool disorder = false;
  std::string disorder_value = "3+s";
  bool tls_record = true;
  std::string tls_value = "1+s";
  bool auto_retry = true;
  bool http_modification = false;
  bool fake_packet = false;
  int fake_ttl = 8;
};

inline bool ValidPreset(std::string_view preset) {
  return preset == "balanced" || preset == "split" || preset == "disorder" ||
         preset == "aggressive" || preset == "custom";
}

// Same bounded position grammar as the existing Dart DpiOptions. Input is
// passed as individual process arguments, never interpreted by a shell.
inline bool ValidPosition(std::string_view value) {
  size_t index = 0;
  if (!value.empty() && value.front() == '-')
    ++index;
  auto digits = [&](size_t maximum) {
    size_t start = index;
    while (index < value.size() && value[index] >= '0' && value[index] <= '9')
      ++index;
    return index > start && index - start <= maximum;
  };
  if (!digits(5))
    return false;
  for (int group = 0; index < value.size() && value[index] == ':'; ++group) {
    if (group == 2)
      return false;
    ++index;
    if (!digits(3))
      return false;
  }
  if (index == value.size())
    return true;
  if (value[index++] != '+')
    return false;
  size_t start = index;
  for (; index < value.size(); ++index) {
    if (std::string_view("shnem").find(value[index]) == std::string_view::npos)
      return false;
  }
  return index > start && index - start <= 3;
}

inline bool ValidCustomOptions(const CustomDpiOptions& options) {
  return (!options.split || ValidPosition(options.split_value)) &&
         (!options.disorder || ValidPosition(options.disorder_value)) &&
         (!options.tls_record || ValidPosition(options.tls_value)) &&
         options.split_value.size() <= 32 && options.disorder_value.size() <= 32 &&
         options.tls_value.size() <= 32 && options.fake_ttl >= 1 && options.fake_ttl <= 64;
}

inline std::optional<std::vector<std::string>> DpiArguments(
    std::string_view preset, bool windows, const CustomDpiOptions& options = {}) {
  if (!ValidPreset(preset))
    return std::nullopt;
  if (preset == "custom") {
    if (!ValidCustomOptions(options))
      return std::nullopt;
    std::vector<std::string> result;
    auto append = [&](bool enabled, const char* flag, const std::string& value) {
      if (enabled) {
        result.emplace_back(flag);
        result.push_back(value);
      }
    };
    append(options.split, "--split", options.split_value);
    append(options.disorder, "--disorder", options.disorder_value);
    append(options.tls_record, "--tlsrec", options.tls_value);
    append(options.auto_retry, "--auto", "torst");
    append(options.http_modification, "--mod-http", "h,d");
    if (options.fake_packet) {
      result.insert(result.end(), {"--fake", "1", "--ttl", std::to_string(options.fake_ttl)});
    }
    return result;
  }
  std::vector<std::string> result = {"--split", "1+s"};
  if (preset == "disorder" || preset == "aggressive")
    result.insert(result.end(), {"--disorder", windows ? "3+s" : "1"});
  if (preset == "balanced" || preset == "aggressive")
    result.insert(result.end(), {"--auto", "torst"});
  if (preset != "disorder")
    result.insert(result.end(), {"--tlsrec", "1+s"});
  if (preset == "aggressive")
    result.insert(result.end(), {"--mod-http", "h,d"});
  return result;
}
}  // namespace internet_browser
#endif
