#ifndef CHROME_BROWSER_INTERNET_BROWSER_DPI_CONFIGURATION_H_
#define CHROME_BROWSER_INTERNET_BROWSER_DPI_CONFIGURATION_H_

#include <utility>

#include "base/values.h"
#include "chrome/browser/internet_browser/dpi_options.h"

namespace internet_browser {
inline std::optional<CustomDpiOptions> ReadCustomOptions(const base::DictValue& data) {
  CustomDpiOptions options;
  auto boolean = [&](const char* key, bool& destination) {
    const auto* value = data.Find(key);
    if (!value)
      return true;
    if (!value->is_bool())
      return false;
    destination = value->GetBool();
    return true;
  };
  auto position = [&](const char* key, std::string& destination) {
    const auto* value = data.Find(key);
    if (!value)
      return true;
    if (!value->is_string() || value->GetString().size() > 32)
      return false;
    destination = value->GetString();
    return true;
  };
  if (!boolean("split", options.split) || !boolean("disorder", options.disorder) ||
      !boolean("tlsRecord", options.tls_record) || !boolean("autoRetry", options.auto_retry) ||
      !boolean("httpModification", options.http_modification) || !boolean("fakePacket", options.fake_packet) ||
      !position("splitValue", options.split_value) || !position("disorderValue", options.disorder_value) ||
      !position("tlsValue", options.tls_value))
    return std::nullopt;
  if (const auto* ttl = data.Find("fakeTtl")) {
    if (!ttl->is_int())
      return std::nullopt;
    options.fake_ttl = ttl->GetInt();
  }
  return ValidCustomOptions(options) ? std::optional(options) : std::nullopt;
}

inline base::DictValue CustomOptionsDictionary(const CustomDpiOptions& options) {
  base::DictValue result;
  result.Set("split", options.split);
  result.Set("splitValue", options.split_value);
  result.Set("disorder", options.disorder);
  result.Set("disorderValue", options.disorder_value);
  result.Set("tlsRecord", options.tls_record);
  result.Set("tlsValue", options.tls_value);
  result.Set("autoRetry", options.auto_retry);
  result.Set("httpModification", options.http_modification);
  result.Set("fakePacket", options.fake_packet);
  result.Set("fakeTtl", options.fake_ttl);
  return result;
}

// Read through the original preference snapshot only until a native config
// exists. The user's later native choices always take precedence.
inline base::DictValue LegacyDpiConfiguration(const base::DictValue& settings) {
  base::DictValue result;
  auto enabled = settings.FindBool("dpi_enabled");
  if (!enabled)
    return result;
  std::string preset = "balanced";
  if (const auto* saved = settings.FindString("dpi_options_preset"))
    preset = *saved;
  base::DictValue custom;
  const std::pair<const char*, const char*> keys[] = {
      {"split", "dpi_options_split"}, {"splitValue", "dpi_options_split_value"},
      {"disorder", "dpi_options_disorder"}, {"disorderValue", "dpi_options_disorder_value"},
      {"tlsRecord", "dpi_options_tls"}, {"tlsValue", "dpi_options_tls_value"},
      {"autoRetry", "dpi_options_auto"}, {"httpModification", "dpi_options_http"},
      {"fakePacket", "dpi_options_fake"}, {"fakeTtl", "dpi_options_ttl"}};
  for (const auto& [name, legacy] : keys) {
    if (const auto* value = settings.Find(legacy))
      custom.Set(name, value->Clone());
  }
  auto options = ReadCustomOptions(custom);
  result.Set("enabled", *enabled);
  result.Set("preset", ValidPreset(preset) && options ? preset : "invalid");
  if (options)
    result.Set("custom", CustomOptionsDictionary(*options));
  result.Set("migratedFromLegacy", true);
  return result;
}
}  // namespace internet_browser
#endif
