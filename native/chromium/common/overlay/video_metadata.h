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
#include "base/strings/string_util.h"
#include "base/strings/utf_string_conversions.h"
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
inline std::string NormalizeVideoTitle(const std::string& title) {
  if (title.size() > 8192 || !base::IsStringUTF8(title)) return {};
  auto text = base::UTF8ToUTF16(title);
  for (auto& character : text)
    if (character < 0x20 || character == 0x7f) character = u' ';
  text = base::CollapseWhitespace(text, false);
  if (text.size() > 180) {
    text.resize(180);
    if (text.back() >= 0xd800 && text.back() <= 0xdbff) text.pop_back();
  }
  return base::UTF16ToUTF8(text);
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
  if (const auto* saved = native.FindDict(name)) {
    if (saved->Find("lastPositionMs"))
      item.Set("lastPositionMs", VideoPosition(*saved));
    if (const auto* page = saved->FindString("sourcePage"); page && page->size() <= 4096)
      item.Set("sourcePage", *page);
    if (const auto* title = saved->FindString("title")) {
      auto normalized = NormalizeVideoTitle(*title);
      if (!normalized.empty()) item.Set("title", normalized);
    }
  }
}
inline bool SaveVideoPosition(const base::FilePath& file, const std::string& name,
                              double position, double duration) {
  if (file.empty() || name.empty() || name.size() > 1024 ||
      !std::isfinite(position) || !std::isfinite(duration) || position < 0 ||
      duration < 0 || position > 604800000 || duration > 604800000)
    return false;
  base::AutoLock lock(VideoStateLock());
  auto state = ReadVideoState(file);
  const auto* previous = state.FindDict(name);
  auto item = previous ? previous->Clone() : base::DictValue();
  item.Set("lastPositionMs", position);
  item.Set("durationMs", duration);
  state.Set(name, std::move(item));
  std::string serialized;
  return base::JSONWriter::Write(state, &serialized) && serialized.size() <= 4 * 1024 * 1024 &&
      base::ImportantFileWriter::WriteFileAtomically(file, serialized);
}
inline bool SaveVideoTitle(const base::FilePath& file, const std::string& name,
                           const std::string& title) {
  const auto normalized = NormalizeVideoTitle(title);
  if (file.empty() || name.empty() || name.size() > 1024 || normalized.empty()) return false;
  base::AutoLock lock(VideoStateLock());
  auto state = ReadVideoState(file);
  const auto* previous = state.FindDict(name);
  auto item = previous ? previous->Clone() : base::DictValue();
  item.Set("title", normalized);
  state.Set(name, std::move(item));
  std::string serialized;
  return base::JSONWriter::Write(state, &serialized) && serialized.size() <= 4 * 1024 * 1024 &&
      base::ImportantFileWriter::WriteFileAtomically(file, serialized);
}
inline base::DictValue MergeVideoCatalog(const base::FilePath& file,
                                         const base::DictValue& defaults) {
  if (file.empty()) return {};
  base::AutoLock lock(VideoStateLock());
  auto state = ReadVideoState(file);
  bool changed = false;
  for (const auto [key, value] : defaults) {
    if (key.empty() || key.size() > 1024 || !value.is_dict()) continue;
    const auto* previous = state.FindDict(key);
    auto item = previous ? previous->Clone() : base::DictValue();
    if (!item.FindString("title")) {
      if (const auto* title = value.GetDict().FindString("title")) {
        auto normalized = NormalizeVideoTitle(*title);
        if (!normalized.empty()) {item.Set("title", normalized); changed = true;}
      }
    }
    if (!item.FindString("sourcePage")) {
      if (const auto* page = value.GetDict().FindString("sourcePage"); page && !page->empty() && page->size() <= 4096) {
        item.Set("sourcePage", *page); changed = true;
      }
    }
    state.Set(key, std::move(item));
  }
  if (changed) {
    std::string serialized;
    if (base::JSONWriter::Write(state, &serialized) && serialized.size() <= 4 * 1024 * 1024)
      base::ImportantFileWriter::WriteFileAtomically(file, serialized);
  }
  return state;
}
}  // namespace internet_browser
#endif
