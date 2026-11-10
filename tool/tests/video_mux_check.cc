// Standalone checks for native/chromium/common/overlay/video_mux.h.
//   video_mux_check                      synthetic unit checks
//   video_mux_check VIDEO AUDIO OUTPUT   mux real files (used by
//                                        video_mux_media_test.py with ffmpeg)
#include <cassert>
#include <cstdio>
#include <iostream>
#include <map>
#include <string>
#include <vector>
#include "native/chromium/common/overlay/video_mux.h"

namespace {
using Bytes = std::vector<uint8_t>;
using internet_browser::Mp4Sink;
using internet_browser::Mp4Source;
using internet_browser::MuxFragmentedMp4;

class MemorySource : public Mp4Source {
 public:
  explicit MemorySource(Bytes data) : data_(std::move(data)) {}
  uint64_t Size() override { return data_.size(); }
  bool Read(uint64_t offset, size_t size, Bytes& out) override {
    if (offset > data_.size() || size > data_.size() - offset) return false;
    out.assign(data_.begin() + long(offset), data_.begin() + long(offset + size));
    return true;
  }
 private:
  Bytes data_;
};
class MemorySink : public Mp4Sink {
 public:
  bool Write(const Bytes& data, size_t size) override { out.insert(out.end(), data.begin(), data.begin() + long(size)); return true; }
  Bytes out;
};
class FileSource : public Mp4Source {
 public:
  explicit FileSource(const char* path) : file_(std::fopen(path, "rb")) {}
  ~FileSource() override { if (file_) std::fclose(file_); }
  bool ok() const { return file_ != nullptr; }
  uint64_t Size() override { std::fseek(file_, 0, SEEK_END); return uint64_t(std::ftell(file_)); }
  bool Read(uint64_t offset, size_t size, Bytes& out) override {
    out.resize(size);
    return std::fseek(file_, long(offset), SEEK_SET) == 0 && std::fread(out.data(), 1, size, file_) == size;
  }
 private:
  std::FILE* file_;
};
class FileSink : public Mp4Sink {
 public:
  explicit FileSink(const char* path) : file_(std::fopen(path, "wb")) {}
  ~FileSink() override { if (file_) std::fclose(file_); }
  bool Write(const Bytes& data, size_t size) override { return file_ && std::fwrite(data.data(), 1, size, file_) == size; }
 private:
  std::FILE* file_;
};

void U32(Bytes& b, uint32_t v) { for (int s = 24; s >= 0; s -= 8) b.push_back(uint8_t(v >> s)); }
void U64(Bytes& b, uint64_t v) { U32(b, uint32_t(v >> 32)); U32(b, uint32_t(v)); }
void Zeros(Bytes& b, size_t n) { b.insert(b.end(), n, 0); }
Bytes Box(const char* type, const Bytes& payload) {
  Bytes b; U32(b, uint32_t(payload.size() + 8)); b.insert(b.end(), type, type + 4);
  b.insert(b.end(), payload.begin(), payload.end()); return b;
}
Bytes Cat(std::initializer_list<Bytes> parts) { Bytes b; for (const auto& p : parts) b.insert(b.end(), p.begin(), p.end()); return b; }
Bytes Full(uint8_t version, uint32_t flags, const Bytes& rest) {
  Bytes b{version, uint8_t(flags >> 16), uint8_t(flags >> 8), uint8_t(flags)}; b.insert(b.end(), rest.begin(), rest.end()); return b;
}
Bytes Mvhd(uint32_t timescale, uint32_t duration) {
  Bytes p; U32(p, 0); U32(p, 0); U32(p, timescale); U32(p, duration); Zeros(p, 76); U32(p, 9);
  return Box("mvhd", Full(0, 0, p));
}
Bytes Trak(uint32_t id, uint32_t media_timescale, const char* handler, uint32_t tkhd_duration = 0,
           const char* sample_entry = "avc1", uint32_t edit_duration = 0) {
  Bytes tk; U32(tk, 0); U32(tk, 0); U32(tk, id); U32(tk, 0); U32(tk, tkhd_duration); Zeros(tk, 60);
  Bytes md; U32(md, 0); U32(md, 0); U32(md, media_timescale); U32(md, 0); U32(md, 0);
  Bytes hd; U32(hd, 0); hd.insert(hd.end(), handler, handler + 4); Zeros(hd, 13);
  Bytes stsd; U32(stsd, 1); stsd = Cat({stsd, Box(sample_entry, Bytes(16, 0))});
  Bytes trak = Box("tkhd", Full(0, 3, tk));
  if (edit_duration) {
    Bytes el; U32(el, 1); U32(el, edit_duration); U32(el, 0); U32(el, 0x00010000);
    trak = Cat({trak, Box("edts", Box("elst", Full(0, 0, el)))});
  }
  return Box("trak", Cat({trak, Box("mdia", Cat({Box("mdhd", Full(0, 0, md)), Box("hdlr", Full(0, 0, hd)),
      Box("minf", Box("stbl", Box("stsd", Full(0, 0, stsd))))}))}));
}
Bytes Trex(uint32_t id) { Bytes p; U32(p, id); U32(p, 1); U32(p, 0); U32(p, 0); U32(p, 0); return Box("trex", Full(0, 0, p)); }
Bytes Mehd(uint32_t duration) { Bytes p; U32(p, duration); return Box("mehd", Full(0, 0, p)); }
Bytes Ftyp() { Bytes p{'i', 's', 'o', '5'}; U32(p, 0); p.insert(p.end(), {'i', 's', 'o', '6'}); return Box("ftyp", p); }
// moof + mdat. |absolute| writes tfhd base_data_offset = |file_offset| + moof size + 8.
Bytes Fragment(uint32_t id, uint32_t sequence, uint64_t time, const std::string& media, bool absolute, uint64_t file_offset,
               bool with_tfdt = true) {
  Bytes mf; U32(mf, sequence);
  const auto build = [&](uint64_t base) {
    Bytes th; U32(th, id); if (absolute) U64(th, base);
    Bytes tr; U32(tr, 1); U32(tr, 0);  // sample_count, data_offset (patched below).
    Bytes traf = Box("tfhd", Full(0, absolute ? 0x1 : 0x020000, th));
    if (with_tfdt) { Bytes td; U64(td, time); traf = Cat({traf, Box("tfdt", Full(1, 0, td))}); }
    traf = Cat({traf, Box("trun", Full(0, 0x1, tr))});
    return Box("moof", Cat({Box("mfhd", Full(0, 0, mf)), Box("traf", traf)}));
  };
  Bytes moof = build(0);
  const uint64_t data = file_offset + moof.size() + 8;
  moof = build(data);
  // trun data_offset: relative to base (absolute) or to the moof start.
  const uint32_t relative = absolute ? 0 : uint32_t(moof.size() + 8);
  for (size_t i = 0; i + 4 <= moof.size(); ++i)
    if (std::string(moof.begin() + long(i), moof.begin() + long(i + 4)) == "trun") {
      const size_t at = i + 4 + 4 + 4;
      for (int s = 0; s < 4; ++s) moof[at + size_t(s)] = uint8_t(relative >> (24 - 8 * s));
    }
  return Cat({moof, Box("mdat", Bytes(media.begin(), media.end()))});
}

struct Parsed {
  std::vector<std::pair<std::string, Bytes>> top;
};
std::vector<std::pair<std::string, Bytes>> Boxes(const Bytes& b, size_t start, size_t end) {
  std::vector<std::pair<std::string, Bytes>> result;
  while (start < end) {
    const uint32_t size = (uint32_t(b[start]) << 24) | (uint32_t(b[start + 1]) << 16) | (uint32_t(b[start + 2]) << 8) | b[start + 3];
    assert(size >= 8 && start + size <= end);
    result.emplace_back(std::string(b.begin() + long(start + 4), b.begin() + long(start + 8)),
                        Bytes(b.begin() + long(start), b.begin() + long(start + size)));
    start += size;
  }
  return result;
}
uint32_t Read32(const Bytes& b, size_t at) { return (uint32_t(b[at]) << 24) | (uint32_t(b[at + 1]) << 16) | (uint32_t(b[at + 2]) << 8) | b[at + 3]; }
uint64_t Read64(const Bytes& b, size_t at) { return (uint64_t(Read32(b, at)) << 32) | Read32(b, at + 4); }
// Depth-first search for the first box of |type| inside |box| (containers only).
const Bytes* Descend(const Bytes& box, const std::vector<std::string>& path, size_t level = 0) {
  if (level == path.size()) return &box;
  static std::vector<Bytes> keep;
  for (const auto& [type, child] : Boxes(box, 8, box.size()))
    if (type == path[level]) { keep.push_back(child); return Descend(keep.back(), path, level + 1); }
  return nullptr;
}

bool Mux(const Bytes& video, const Bytes& audio, Bytes* out = nullptr, std::string* error = nullptr) {
  MemorySource v(video), a(audio); MemorySink sink;
  const bool ok = MuxFragmentedMp4(v, a, sink, error);
  if (out) *out = sink.out;
  return ok;
}

Bytes VideoInput(bool tfdt = true) {
  Bytes init = Cat({Ftyp(), Box("moov", Cat({Mvhd(1000, 0), Trak(7, 90000, "vide"), Box("mvex", Trex(7))}))});
  Bytes file = init;
  // 3 fragments of 2 s (180000 ticks at 90 kHz).
  for (uint32_t i = 0; i < 3; ++i)
    file = Cat({file, Box("styp", Bytes(8, 0)), Fragment(7, i + 1, i * 180000ULL, "V" + std::to_string(i), false, file.size() + 16, tfdt)});
  return file;
}
Bytes AudioInput() {
  // Different movie timescale (48000) to exercise rescaling, absolute base offsets.
  Bytes init = Cat({Ftyp(), Box("moov", Cat({Mvhd(48000, 288000), Trak(1, 44100, "soun", 288000, "mp4a", 240000),
                                             Box("mvex", Cat({Mehd(288000), Trex(1)}))}))});
  Bytes file = init;
  // 6 fragments of 1 s (44100 ticks).
  for (uint32_t i = 0; i < 6; ++i)
    file = Cat({file, Fragment(1, i + 1, i * 44100ULL, "A" + std::to_string(i), true, file.size())});
  return file;
}

void SyntheticChecks() {
  Bytes out; std::string error;
  const bool muxed = Mux(VideoInput(), AudioInput(), &out, &error);
  if (!muxed) std::cerr << error << "\n";
  assert(muxed);
  const auto top = Boxes(out, 0, out.size());
  assert(top[0].first == "ftyp" && top[1].first == "moov");
  const Bytes& moov = top[1].second;
  // mvhd: movie timescale 1000, duration = audio 288000/48000 s = 6000, next track 3.
  const Bytes* mvhd = Descend(moov, {"mvhd"});
  assert(mvhd && Read32(*mvhd, 20) == 1000 && Read32(*mvhd, 24) == 6000 && Read32(*mvhd, mvhd->size() - 4) == 3);
  std::vector<uint32_t> track_ids;
  for (const auto& [type, child] : Boxes(moov, 8, moov.size())) {
    if (type != "trak") continue;
    const Bytes* tkhd = Descend(child, {"tkhd"});
    track_ids.push_back(Read32(*tkhd, 20));
    if (Read32(*tkhd, 20) == 2) {
      assert(Read32(*tkhd, 28) == 6000);  // Rescaled from 48000 to 1000.
      const Bytes* elst = Descend(child, {"edts", "elst"});
      assert(elst && Read32(*elst, 16) == 5000);  // 240000 / 48.
    }
  }
  assert((track_ids == std::vector<uint32_t>{1, 2}));
  const Bytes* mvex = Descend(moov, {"mvex"});
  std::vector<uint32_t> trex_ids; uint64_t mehd = 0;
  for (const auto& [type, child] : Boxes(*mvex, 8, mvex->size())) {
    if (type == "trex") trex_ids.push_back(Read32(child, 12));
    if (type == "mehd") { assert(child[8] == 1); mehd = Read64(child, 12); }
  }
  assert((trex_ids == std::vector<uint32_t>{1, 2}) && mehd == 6000);

  // Fragments interleaved by time (video 0,2,4 s; audio 0..5 s), styp dropped,
  // sequence numbers 1..9, and every trun points at its own mdat payload.
  std::vector<std::string> order; uint32_t expected_sequence = 1;
  size_t offset = top[0].second.size() + top[1].second.size();
  for (size_t i = 2; i < top.size(); i += 2) {
    assert(top[i].first == "moof" && top[i + 1].first == "mdat");
    const Bytes& moof = top[i].second;
    const Bytes* mfhd = Descend(moof, {"mfhd"});
    assert(Read32(*mfhd, 12) == expected_sequence++);
    const Bytes* tfhd = Descend(moof, {"traf", "tfhd"});
    const uint32_t id = Read32(*tfhd, 12);
    const uint32_t flags = Read32(*tfhd, 8) & 0xFFFFFF;
    const Bytes* trun = Descend(moof, {"traf", "trun"});
    const uint32_t data_offset = Read32(*trun, 16);
    const uint64_t base = (flags & 1) ? Read64(*tfhd, 16) : offset;
    const uint64_t payload = base + data_offset;
    assert(payload == offset + moof.size() + 8);
    const std::string media(out.begin() + long(payload), out.begin() + long(offset + moof.size() + top[i + 1].second.size()));
    order.push_back(media);
    assert(media[0] == (id == 1 ? 'V' : 'A'));
    offset += moof.size() + top[i + 1].second.size();
  }
  assert((order == std::vector<std::string>{"V0", "A0", "A1", "V1", "A2", "A3", "V2", "A4", "A5"}));

  // Rejections: the caller keeps separate files instead.
  assert(!Mux(AudioInput(), VideoInput()));                       // Handlers swapped.
  assert(!Mux(VideoInput(false), AudioInput()));                  // No tfdt.
  Bytes progressive = Cat({Ftyp(), Box("moov", Cat({Mvhd(1000, 0), Trak(1, 90000, "vide"), Box("mvex", Trex(1))})), Box("mdat", Bytes(4, 1))});
  assert(!Mux(progressive, AudioInput()));                        // Media outside fragments.
  Bytes two = Cat({Ftyp(), Box("moov", Cat({Mvhd(1000, 0), Trak(1, 90000, "vide"), Trak(2, 44100, "soun"), Box("mvex", Cat({Trex(1), Trex(2)}))}))});
  assert(!Mux(Cat({two, Fragment(1, 1, 0, "x", false, two.size())}), AudioInput()));  // Already two tracks.
  Bytes encrypted = Cat({Ftyp(), Box("moov", Cat({Mvhd(1000, 0), Trak(1, 90000, "vide", 0, "encv"), Box("mvex", Trex(1))}))});
  assert(!Mux(Cat({encrypted, Fragment(1, 1, 0, "x", false, encrypted.size())}), AudioInput()));
  Bytes video = VideoInput();
  for (size_t cut : {size_t(3), size_t(40), video.size() - 3}) {      // Truncated input never crashes.
    Bytes truncated(video.begin(), video.begin() + long(cut));
    assert(!Mux(truncated, AudioInput()));
  }
  Bytes wrong_id = Cat({Ftyp(), Box("moov", Cat({Mvhd(1000, 0), Trak(1, 90000, "vide"), Box("mvex", Trex(1))}))});
  assert(!Mux(Cat({wrong_id, Fragment(5, 1, 0, "x", false, wrong_id.size())}), AudioInput()));  // tfhd/track mismatch.
  // Corrupt box sizes everywhere must fail cleanly (sanitizers catch overreads).
  for (size_t at = 0; at + 4 <= video.size(); at += 7) {
    Bytes corrupt = video; corrupt[at] ^= 0x80;
    Mux(corrupt, AudioInput());
  }
}
}  // namespace

int main(int argc, char** argv) {
  if (argc == 4) {
    FileSource video(argv[1]), audio(argv[2]);
    if (!video.ok() || !audio.ok()) { std::cerr << "cannot open inputs\n"; return 2; }
    FileSink sink(argv[3]);
    std::string error;
    if (!MuxFragmentedMp4(video, audio, sink, &error)) { std::cerr << "mux failed: " << error << "\n"; return 1; }
    return 0;
  }
  SyntheticChecks();
  std::cout << "Fragmented MP4 video/audio mux checks passed.\n";
  return 0;
}
