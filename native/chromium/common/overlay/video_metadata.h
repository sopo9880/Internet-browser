#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_METADATA_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_METADATA_H_

#include <cmath>
#include <string>
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/files/important_file_writer.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/no_destructor.h"
#include "base/synchronization/lock.h"
#include "base/values.h"

namespace internet_browser {
inline base::Lock& VideoStateLock() {
  static base::NoDestructor<base::Lock> lock;
  return *lock;
}
inline base::DictValue ReadVideoState(const base::FilePath& file) {
  std::string data;
  if (file.empty() || !base::ReadFileToStringWithMaxSize(file, &data, 4 * 1024 * 1024))
    return {};
  auto value = base::JSONReader::ReadDict(data, base::JSON_PARSE_RFC);
  return value ? std::move(*value) : base::DictValue();
}
inline double VideoPosition(const base::DictValue& data) {
  double position = data.FindDouble("lastPositionMs").value_or(0);
  return std::isfinite(position) && position >= 0 && position <= 604800000 ? position : 0;
}
inline void AddVideoMetadata(base::DictValue& item, const std::string& name,
                             const base::DictValue* legacy,
                             const base::DictValue& native) {
  item.Set("name", name);
  item.Set("lastPositionMs", legacy ? VideoPosition(*legacy) : 0);
  if (legacy) {
    for (const char* field : {"title", "quality", "sourcePage"}) {
      if (const auto* value = legacy->FindString(field); value && value->size() <= 4096)
        item.Set(field, *value);
    }
  }
  if (const auto* saved = native.FindDict(name))
    item.Set("lastPositionMs", VideoPosition(*saved));
}
inline bool SaveVideoPosition(const base::FilePath& file, const std::string& name,
                              double position, double duration) {
  if (file.empty() || name.empty() || name.size() > 1024 ||
      !std::isfinite(position) || !std::isfinite(duration) || position < 0 ||
      duration < 0 || position > 604800000 || duration > 604800000)
    return false;
  base::AutoLock lock(VideoStateLock());
  auto state = ReadVideoState(file);
  base::DictValue item;
  item.Set("lastPositionMs", position);
  item.Set("durationMs", duration);
  state.Set(name, std::move(item));
  std::string serialized;
  return base::JSONWriter::Write(state, &serialized) && serialized.size() <= 4 * 1024 * 1024 &&
      base::ImportantFileWriter::WriteFileAtomically(file, serialized);
}
}  // namespace internet_browser
#endif
