#include "native/chromium/common/overlay/dpi_options.h"

#include <iostream>
#include <stdexcept>

namespace {
void Require(bool condition, const char* message) {
  if (!condition)
    throw std::runtime_error(message);
}
void Preset(const char* name, bool windows, std::vector<std::string> expected) {
  auto actual = internet_browser::DpiArguments(name, windows);
  Require(actual.has_value() && *actual == expected, "Preset differs from existing Dart options");
}
}  // namespace

int main() {
  using namespace internet_browser;
  for (const auto* value : {"0", "1+s", "-1+e", "12345:123:999+shm", "1:2", "1:2:3"})
    Require(ValidPosition(value), "A valid legacy position was rejected");
  for (const auto* value : {"", "-", "+1", "123456", "1:1234", "1:2:3:4", "1+ssss",
                            "1+x", "1+s --fake", "1;dir", "1\n", "1++s"})
    Require(!ValidPosition(value), "An invalid position was accepted");
  for (bool windows : {false, true}) {
    Preset("balanced", windows, {"--split", "1+s", "--auto", "torst", "--tlsrec", "1+s"});
    Preset("split", windows, {"--split", "1+s", "--tlsrec", "1+s"});
    Preset("disorder", windows, {"--split", "1+s", "--disorder", windows ? "3+s" : "1"});
    Preset("aggressive", windows, {"--split", "1+s", "--disorder", windows ? "3+s" : "1",
                                  "--auto", "torst", "--tlsrec", "1+s", "--mod-http", "h,d"});
  }
  CustomDpiOptions custom;
  Require(DpiArguments("custom", false, custom).value() == std::vector<std::string>(
      {"--split", "1+s", "--tlsrec", "1+s", "--auto", "torst"}),
      "Default custom option order changed");
  custom.split_value = "-1+e";
  custom.disorder = true;
  custom.tls_record = false;
  custom.auto_retry = false;
  custom.http_modification = true;
  custom.fake_packet = true;
  custom.fake_ttl = 64;
  const std::vector<std::string> expected = {"--split", "-1+e", "--disorder", "3+s",
                                           "--mod-http", "h,d", "--fake", "1", "--ttl", "64"};
  Require(DpiArguments("custom", false, custom).value() == expected, "Custom argument semantics changed");
  custom.fake_ttl = 65;
  Require(!DpiArguments("custom", true, custom), "Out-of-range TTL accepted");
  custom.fake_ttl = 0;
  Require(!DpiArguments("custom", true, custom), "Zero TTL accepted");
  custom.fake_ttl = 8;
  custom.split_value = "1+s;unexpected";
  Require(!DpiArguments("custom", true, custom), "Invalid custom argument accepted");
  Require(!DpiArguments("unknown", true), "Unknown preset accepted");
  custom.split = custom.disorder = custom.fake_packet = custom.http_modification = false;
  Require(DpiArguments("custom", true, custom)->empty(), "Disabled options unexpectedly applied");
  std::cout << "Native DPI legacy preset, custom option and rejection checks passed\n";
}
