#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_MUX_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_MUX_H_
// Combines a video-only and an audio-only fragmented MP4 (ISO BMFF with
// moov/mvex + moof/mdat fragments) into one two-track fragmented MP4.
//
// Saved streams used to keep video.mp4 and audio.mp4 side by side and play
// them through a second <audio> element. That drifts, cannot be shared with
// other apps and breaks system playback. Fragments are copied unchanged; only
// box metadata is rewritten:
//   - track IDs become 1 (video) and 2 (audio) in tkhd/trex/tfhd,
//   - mfhd sequence numbers become strictly increasing across the output,
//   - an absolute tfhd base_data_offset is relocated with its fragment,
//   - audio movie-timescale values (tkhd/elst/mehd) are rescaled when the
//     two movie timescales differ,
//   - fragments are interleaved by decode time so progressive playback reads
//     audio and video together.
// Anything else (non-fragmented input, several tracks, missing tfdt,
// encryption boxes) returns false so the caller can keep the files separate.
//
// No Chromium dependency: Chromium adapts base::File, tests adapt stdio.
#include <algorithm>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace internet_browser {
// |out| is resized to |size|; returns false on a short or failed read.
class Mp4Source {
 public:
  virtual ~Mp4Source() = default;
  virtual uint64_t Size() = 0;
  virtual bool Read(uint64_t offset, size_t size, std::vector<uint8_t>& out) = 0;
};
// Writes the first |size| bytes of |data|.
class Mp4Sink {
 public:
  virtual ~Mp4Sink() = default;
  virtual bool Write(const std::vector<uint8_t>& data, size_t size) = 0;
};

namespace mp4_mux_internal {
inline constexpr uint64_t kMaxMetadataBox = 16 * 1024 * 1024;
inline constexpr size_t kMaxFragments = 200000;
inline constexpr size_t kCopyChunk = 1024 * 1024;

inline uint32_t Fourcc(std::string_view text) {
  return (uint32_t(uint8_t(text[0])) << 24) | (uint32_t(uint8_t(text[1])) << 16) |
         (uint32_t(uint8_t(text[2])) << 8) | uint32_t(uint8_t(text[3]));
}
// Index-based big-endian access; callers bounds-check before use and
// std::vector indexing is hardened in Chromium builds.
inline uint32_t Get32(const std::vector<uint8_t>& d, uint64_t at) {
  const size_t i = size_t(at);
  return (uint32_t(d[i]) << 24) | (uint32_t(d[i + 1]) << 16) | (uint32_t(d[i + 2]) << 8) | uint32_t(d[i + 3]);
}
inline uint64_t Get64(const std::vector<uint8_t>& d, uint64_t at) { return (uint64_t(Get32(d, at)) << 32) | Get32(d, at + 4); }
inline void Put32(std::vector<uint8_t>& d, uint64_t at, uint32_t v) {
  const size_t i = size_t(at);
  d[i] = uint8_t(v >> 24); d[i + 1] = uint8_t(v >> 16); d[i + 2] = uint8_t(v >> 8); d[i + 3] = uint8_t(v);
}
inline void Put64(std::vector<uint8_t>& d, uint64_t at, uint64_t v) { Put32(d, at, uint32_t(v >> 32)); Put32(d, at + 4, uint32_t(v)); }

struct Box {
  uint32_t type = 0;
  uint64_t offset = 0;  // Start of the box header.
  uint64_t size = 0;    // Whole box, header included.
  uint64_t header = 0;  // 8 or 16 bytes.
};
// Box header at |offset| within [offset, end).
inline std::optional<Box> ReadBoxHeader(Mp4Source& source, uint64_t offset, uint64_t end) {
  if (offset > end || end - offset < 8) return std::nullopt;
  std::vector<uint8_t> raw;
  if (!source.Read(offset, 8, raw)) return std::nullopt;
  Box box{Get32(raw, 4), offset, Get32(raw, 0), 8};
  if (box.size == 1) {
    if (end - offset < 16 || !source.Read(offset + 8, 8, raw)) return std::nullopt;
    box.size = Get64(raw, 0); box.header = 16;
  } else if (box.size == 0) {
    box.size = end - offset;
  }
  if (box.size < box.header || box.size > end - offset) return std::nullopt;
  return box;
}
// Same, inside an in-memory buffer.
inline std::optional<Box> MemoryBox(const std::vector<uint8_t>& data, uint64_t offset, uint64_t end) {
  if (end > data.size() || offset > end || end - offset < 8) return std::nullopt;
  Box box{Get32(data, offset + 4), offset, Get32(data, offset), 8};
  if (box.size == 1) {
    if (end - offset < 16) return std::nullopt;
    box.size = Get64(data, offset + 8); box.header = 16;
  } else if (box.size == 0) {
    box.size = end - offset;
  }
  if (box.size < box.header || box.size > end - offset) return std::nullopt;
  return box;
}
// Direct children of the box spanning [begin, end) whose payload starts at |begin|.
inline std::optional<std::vector<Box>> Children(const std::vector<uint8_t>& data, uint64_t begin, uint64_t end) {
  std::vector<Box> result;
  while (begin < end) {
    const auto box = MemoryBox(data, begin, end);
    if (!box || result.size() >= 4096) return std::nullopt;
    result.push_back(*box);
    begin += box->size;
  }
  return result;
}
inline const Box* Find(const std::vector<Box>& boxes, const char* type) {
  for (const auto& box : boxes) if (box.type == Fourcc(type)) return &box;
  return nullptr;
}
inline size_t Count(const std::vector<Box>& boxes, const char* type) {
  return size_t(std::count_if(boxes.begin(), boxes.end(), [&](const Box& box) { return box.type == Fourcc(type); }));
}
inline bool LoadBox(Mp4Source& source, const Box& box, std::vector<uint8_t>& out) {
  if (box.size > kMaxMetadataBox) return false;
  return source.Read(box.offset, size_t(box.size), out);
}
// Full-box payload with at least |need| bytes after version/flags.
inline bool FullBox(const std::vector<uint8_t>& data, const Box& box, uint64_t need, uint8_t* version) {
  if (box.size < box.header + 4 + need) return false;
  *version = data[size_t(box.offset + box.header)];
  return true;
}
// Like FullBox, with separate payload requirements for version 0 and 1.
inline bool VersionedBox(const std::vector<uint8_t>& data, const Box& box, uint64_t need0, uint64_t need1, uint8_t* version) {
  if (!FullBox(data, box, 0, version) || *version > 1) return false;
  return FullBox(data, box, *version ? need1 : need0, version);
}
inline uint64_t Rescale(uint64_t value, uint32_t from, uint32_t to) {
  if (from == to || from == 0) return value;
  const long double scaled = (long double)value * to / from;
  return scaled >= 18446744073709551615.0L ? UINT64_MAX : uint64_t(scaled + 0.5L);
}

struct Track {
  std::vector<uint8_t> ftyp;
  std::vector<uint8_t> moov;
  // Children of moov other than mvhd/trak/mvex (kept from the video input only).
  std::vector<Box> moov_children;
  Box mvhd, trak, mvex;
  uint32_t movie_timescale = 0;
  uint32_t media_timescale = 0;
  uint32_t track_id = 0;
  uint32_t handler = 0;
  std::optional<Box> mehd;
  Box trex;
  struct Fragment {
    uint64_t begin = 0;      // moof offset in the source file.
    uint64_t moof_size = 0;
    uint64_t end = 0;        // End of the moof + mdat unit.
    uint64_t decode_time = 0;
  };
  std::vector<Fragment> fragments;
};

inline bool ParseTrak(Track& track) {
  auto children = Children(track.moov, track.trak.offset + track.trak.header, track.trak.offset + track.trak.size);
  if (!children) return false;
  const Box* tkhd = Find(*children, "tkhd");
  const Box* mdia = Find(*children, "mdia");
  if (!tkhd || !mdia) return false;
  uint8_t version = 0;
  if (!VersionedBox(track.moov, *tkhd, 20, 32, &version)) return false;
  track.track_id = Get32(track.moov, tkhd->offset + tkhd->header + 4 + (version ? 16 : 8));
  auto media = Children(track.moov, mdia->offset + mdia->header, mdia->offset + mdia->size);
  if (!media) return false;
  const Box* mdhd = Find(*media, "mdhd");
  const Box* hdlr = Find(*media, "hdlr");
  if (!mdhd || !hdlr || !FullBox(track.moov, *hdlr, 8, &version)) return false;
  track.handler = Get32(track.moov, hdlr->offset + hdlr->header + 8);
  if (!VersionedBox(track.moov, *mdhd, 16, 28, &version)) return false;
  track.media_timescale = Get32(track.moov, mdhd->offset + mdhd->header + 4 + (version ? 16 : 8));
  // Encrypted sample entries (encv/enca + sinf) are never re-packaged.
  const std::string raw(track.moov.begin() + long(track.trak.offset), track.moov.begin() + long(track.trak.offset + track.trak.size));
  for (const char* marker : {"sinf", "encv", "enca", "tenc", "pssh"})
    if (raw.find(marker) != std::string::npos) return false;
  return track.track_id != 0 && track.media_timescale != 0;
}

inline bool ParseMoov(Track& track) {
  const auto top = MemoryBox(track.moov, 0, track.moov.size());
  if (!top) return false;
  auto children = Children(track.moov, top->header, top->size);
  if (!children || Count(*children, "trak") != 1 || Count(*children, "mvhd") != 1 ||
      Count(*children, "mvex") != 1 || Count(*children, "pssh") != 0) return false;
  track.mvhd = *Find(*children, "mvhd");
  track.trak = *Find(*children, "trak");
  track.mvex = *Find(*children, "mvex");
  for (const auto& box : *children)
    if (box.type != Fourcc("mvhd") && box.type != Fourcc("trak") && box.type != Fourcc("mvex"))
      track.moov_children.push_back(box);
  uint8_t version = 0;
  if (!VersionedBox(track.moov, track.mvhd, 96, 108, &version)) return false;
  track.movie_timescale = Get32(track.moov, track.mvhd.offset + track.mvhd.header + 4 + (version ? 16 : 8));
  if (!track.movie_timescale || !ParseTrak(track)) return false;
  auto extends = Children(track.moov, track.mvex.offset + track.mvex.header, track.mvex.offset + track.mvex.size);
  if (!extends || Count(*extends, "trex") != 1 || Count(*extends, "mehd") > 1) return false;
  track.trex = *Find(*extends, "trex");
  if (!FullBox(track.moov, track.trex, 20, &version) ||
      Get32(track.moov, track.trex.offset + track.trex.header + 4) != track.track_id) return false;
  if (const Box* mehd = Find(*extends, "mehd")) {
    if (!VersionedBox(track.moov, *mehd, 4, 8, &version)) return false;
    track.mehd = *mehd;
  }
  return true;
}

// tfhd/tfdt of a single-traf moof held in memory. Returns false for anything
// outside the supported layout.
inline bool ParseMoof(const std::vector<uint8_t>& moof, uint32_t track_id, uint64_t* decode_time) {
  const auto top = MemoryBox(moof, 0, moof.size());
  if (!top) return false;
  auto children = Children(moof, top->header, top->size);
  if (!children || Count(*children, "traf") != 1 || Count(*children, "mfhd") != 1) return false;
  const Box* traf = Find(*children, "traf");
  auto parts = Children(moof, traf->offset + traf->header, traf->offset + traf->size);
  if (!parts || Count(*parts, "tfhd") != 1 || Count(*parts, "tfdt") != 1) return false;
  for (const char* forbidden : {"senc", "saiz", "saio", "sbgp", "sgpd"})
    if (Count(*parts, forbidden)) return false;
  uint8_t version = 0;
  const Box* tfhd = Find(*parts, "tfhd");
  if (!FullBox(moof, *tfhd, 4, &version) || Get32(moof, tfhd->offset + tfhd->header + 4) != track_id) return false;
  const uint32_t flags = Get32(moof, tfhd->offset + tfhd->header) & 0xFFFFFF;
  if ((flags & 0x1) && !FullBox(moof, *tfhd, 12, &version)) return false;
  const Box* tfdt = Find(*parts, "tfdt");
  if (!VersionedBox(moof, *tfdt, 4, 8, &version)) return false;
  const uint64_t value = tfdt->offset + tfdt->header + 4;
  *decode_time = version ? Get64(moof, value) : Get32(moof, value);
  return true;
}

inline bool Index(Mp4Source& source, Track& track, std::string* error) {
  const uint64_t end = source.Size();
  uint64_t offset = 0;
  bool have_ftyp = false;
  std::vector<uint8_t> moof;
  while (offset < end) {
    const auto box = ReadBoxHeader(source, offset, end);
    if (!box) { *error = "invalid box"; return false; }
    const uint32_t type = box->type;
    if (offset == 0) {
      if (type != Fourcc("ftyp") || !LoadBox(source, *box, track.ftyp)) { *error = "missing ftyp"; return false; }
      have_ftyp = true;
    } else if (type == Fourcc("moov")) {
      if (!track.moov.empty() || !LoadBox(source, *box, track.moov) || !ParseMoov(track)) {
        *error = "unsupported moov"; return false;
      }
    } else if (type == Fourcc("moof")) {
      if (track.moov.empty() || track.fragments.size() >= kMaxFragments || !LoadBox(source, *box, moof)) {
        *error = "unsupported moof"; return false;
      }
      Track::Fragment fragment{box->offset, box->size, 0, 0};
      if (!ParseMoof(moof, track.track_id, &fragment.decode_time)) { *error = "unsupported fragment"; return false; }
      // The unit runs through the first following mdat; offsets inside the
      // moof are relative to it, so nothing between them may be dropped.
      uint64_t cursor = box->offset + box->size;
      bool data = false;
      while (cursor < end && !data) {
        const auto next = ReadBoxHeader(source, cursor, end);
        if (!next || next->type == Fourcc("moof")) break;
        data = next->type == Fourcc("mdat");
        cursor += next->size;
      }
      if (!data) { *error = "fragment without mdat"; return false; }
      fragment.end = cursor;
      if (!track.fragments.empty() && fragment.decode_time < track.fragments.back().decode_time) {
        *error = "fragments out of order"; return false;
      }
      track.fragments.push_back(fragment);
      offset = cursor;
      continue;
    } else if (type == Fourcc("mdat")) {
      *error = "media outside fragments"; return false;  // Progressive MP4.
    } else if (type == Fourcc("mfra") || type == Fourcc("sidx") || type == Fourcc("styp") ||
               type == Fourcc("free") || type == Fourcc("skip") || type == Fourcc("emsg") ||
               type == Fourcc("prft") || type == Fourcc("uuid")) {
      // Indexes/markers that would point into the old layout: dropped.
    } else {
      *error = "unexpected top-level box"; return false;
    }
    offset += box->size;
  }
  if (!have_ftyp || track.moov.empty() || track.fragments.empty()) { *error = "incomplete fragmented mp4"; return false; }
  return true;
}

inline void AppendBox(std::vector<uint8_t>& out, const std::vector<uint8_t>& source, const Box& box) {
  out.insert(out.end(), source.begin() + long(box.offset), source.begin() + long(box.offset + box.size));
}
inline void BeginBox(std::vector<uint8_t>& out, size_t* start, const char* type) {
  *start = out.size();
  out.resize(out.size() + 8);
  Put32(out, *start + 4, Fourcc(type));
}
inline bool EndBox(std::vector<uint8_t>& out, size_t start) {
  const uint64_t size = out.size() - start;
  if (size > UINT32_MAX) return false;
  Put32(out, start, uint32_t(size));
  return true;
}

// Copy of |track|'s trak with tkhd track_ID set and, if needed, movie-timescale
// fields (tkhd duration, elst segment durations) rescaled to |movie_timescale|.
inline bool RewriteTrak(const Track& track, uint32_t id, uint32_t movie_timescale, std::vector<uint8_t>& out) {
  std::vector<uint8_t> trak(track.moov.begin() + long(track.trak.offset),
                            track.moov.begin() + long(track.trak.offset + track.trak.size));
  const auto top = MemoryBox(trak, 0, trak.size());
  if (!top) return false;
  auto children = Children(trak, top->header, top->size);
  if (!children) return false;
  for (const auto& box : *children) {
    uint8_t version = 0;
    if (box.type == Fourcc("tkhd")) {
      if (!VersionedBox(trak, box, 20, 32, &version)) return false;
      const uint64_t p = box.offset + box.header + 4;
      Put32(trak, p + (version ? 16 : 8), id);
      const uint64_t duration = p + (version ? 24 : 16);
      if (version) Put64(trak, duration, Rescale(Get64(trak, duration), track.movie_timescale, movie_timescale));
      else Put32(trak, duration, uint32_t(std::min<uint64_t>(UINT32_MAX, Rescale(Get32(trak, duration), track.movie_timescale, movie_timescale))));
    } else if (box.type == Fourcc("edts")) {
      auto edits = Children(trak, box.offset + box.header, box.offset + box.size);
      if (!edits) return false;
      for (const auto& elst : *edits) {
        if (elst.type != Fourcc("elst")) continue;
        if (!VersionedBox(trak, elst, 4, 4, &version)) return false;
        const uint64_t p = elst.offset + elst.header + 4;
        const uint32_t entries = Get32(trak, p);
        const uint64_t entry_size = version ? 20 : 12;
        if ((elst.size - elst.header - 8) / entry_size < entries) return false;
        for (uint32_t i = 0; i < entries; ++i) {
          const uint64_t entry = p + 4 + i * entry_size;
          if (version) Put64(trak, entry, Rescale(Get64(trak, entry), track.movie_timescale, movie_timescale));
          else Put32(trak, entry, uint32_t(std::min<uint64_t>(UINT32_MAX, Rescale(Get32(trak, entry), track.movie_timescale, movie_timescale))));
        }
      }
    }
  }
  out.insert(out.end(), trak.begin(), trak.end());
  return true;
}

inline uint64_t MovieDuration(const Track& track, const Box& box, uint32_t movie_timescale, uint64_t field) {
  const uint8_t version = track.moov[size_t(box.offset + box.header)];
  const uint64_t p = box.offset + box.header + 4 + field;
  return Rescale(version ? Get64(track.moov, p) : Get32(track.moov, p), track.movie_timescale, movie_timescale);
}

inline bool BuildMoov(const Track& video, const Track& audio, std::vector<uint8_t>& out) {
  size_t moov = 0, mvex = 0;
  BeginBox(out, &moov, "moov");
  // mvhd: keep video's, set duration to the longer track and next_track_ID 3.
  const size_t mvhd = out.size();
  AppendBox(out, video.moov, video.mvhd);
  {
    const uint64_t p = mvhd + video.mvhd.header;
    const uint8_t version = out[size_t(p)];
    const uint64_t duration = p + 4 + (version ? 20 : 12);
    const uint64_t longest = std::max(MovieDuration(video, video.mvhd, video.movie_timescale, version ? 20 : 12),
                                      MovieDuration(audio, audio.mvhd, video.movie_timescale, audio.moov[size_t(audio.mvhd.offset + audio.mvhd.header)] ? 20 : 12));
    if (version) Put64(out, duration, longest);
    else Put32(out, duration, uint32_t(std::min<uint64_t>(UINT32_MAX, longest)));
    Put32(out, mvhd + video.mvhd.size - 4, 3);
  }
  for (const auto& box : video.moov_children) AppendBox(out, video.moov, box);
  if (!RewriteTrak(video, 1, video.movie_timescale, out) || !RewriteTrak(audio, 2, video.movie_timescale, out)) return false;
  BeginBox(out, &mvex, "mvex");
  if (video.mehd || audio.mehd) {
    uint64_t longest = 0;
    for (const Track* track : {&video, &audio})
      if (track->mehd) longest = std::max(longest, MovieDuration(*track, *track->mehd, video.movie_timescale, 0));
    out.insert(out.end(), {0, 0, 0, 20, 'm', 'e', 'h', 'd', 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0});
    Put64(out, out.size() - 8, longest);
  }
  for (const auto& [track, id] : {std::pair{&video, 1u}, std::pair{&audio, 2u}}) {
    const size_t trex = out.size();
    AppendBox(out, track->moov, track->trex);
    Put32(out, trex + track->trex.header + 4, id);
  }
  return EndBox(out, mvex) && EndBox(out, moov);
}

// Rewrites mfhd/tfhd of an in-memory moof that moves from |old_offset| to
// |new_offset| in the output.
inline bool RewriteMoof(std::vector<uint8_t>& moof, uint32_t id, uint32_t sequence, uint64_t old_offset, uint64_t new_offset) {
  const auto top = MemoryBox(moof, 0, moof.size());
  if (!top) return false;
  auto children = Children(moof, top->header, top->size);
  if (!children) return false;
  uint8_t version = 0;
  const Box* mfhd = Find(*children, "mfhd");
  const Box* traf = Find(*children, "traf");
  if (!mfhd || !traf || !FullBox(moof, *mfhd, 4, &version)) return false;
  Put32(moof, mfhd->offset + mfhd->header + 4, sequence);
  auto parts = Children(moof, traf->offset + traf->header, traf->offset + traf->size);
  if (!parts) return false;
  const Box* tfhd = Find(*parts, "tfhd");
  if (!tfhd) return false;
  const uint64_t p = tfhd->offset + tfhd->header;
  Put32(moof, p + 4, id);
  if (Get32(moof, p) & 0x1) {
    // Absolute file offset: shift by however far the fragment moved.
    const uint64_t base = Get64(moof, p + 8);
    if (new_offset >= old_offset) {
      if (base > UINT64_MAX - (new_offset - old_offset)) return false;
      Put64(moof, p + 8, base + (new_offset - old_offset));
    } else {
      if (base < old_offset - new_offset) return false;
      Put64(moof, p + 8, base - (old_offset - new_offset));
    }
  }
  return true;
}
}  // namespace mp4_mux_internal

inline bool MuxFragmentedMp4(Mp4Source& video_source, Mp4Source& audio_source, Mp4Sink& sink, std::string* error) {
  using namespace mp4_mux_internal;
  std::string ignored;
  if (!error) error = &ignored;
  Track video, audio;
  if (!Index(video_source, video, error)) { *error = "video: " + *error; return false; }
  if (!Index(audio_source, audio, error)) { *error = "audio: " + *error; return false; }
  if (video.handler != Fourcc("vide") || audio.handler != Fourcc("soun")) { *error = "unexpected track types"; return false; }

  std::vector<uint8_t> head = video.ftyp;
  if (!BuildMoov(video, audio, head)) { *error = "cannot build moov"; return false; }
  if (!sink.Write(head, head.size())) { *error = "write failed"; return false; }
  uint64_t written = head.size();

  // Interleave by decode time in seconds; ties put video first.
  size_t v = 0, a = 0;
  uint32_t sequence = 0;
  std::vector<uint8_t> moof, buffer;
  while (v < video.fragments.size() || a < audio.fragments.size()) {
    bool take_video = a >= audio.fragments.size();
    if (!take_video && v < video.fragments.size()) {
      const long double vt = (long double)video.fragments[v].decode_time / video.media_timescale;
      const long double at = (long double)audio.fragments[a].decode_time / audio.media_timescale;
      take_video = vt <= at;
    }
    Track& track = take_video ? video : audio;
    Mp4Source& source = take_video ? video_source : audio_source;
    const auto& fragment = track.fragments[take_video ? v++ : a++];
    if (!source.Read(fragment.begin, size_t(fragment.moof_size), moof) ||
        !RewriteMoof(moof, take_video ? 1 : 2, ++sequence, fragment.begin, written) ||
        !sink.Write(moof, moof.size())) {
      *error = "fragment rewrite failed"; return false;
    }
    for (uint64_t offset = fragment.begin + fragment.moof_size; offset < fragment.end;) {
      const size_t count = size_t(std::min<uint64_t>(kCopyChunk, fragment.end - offset));
      if (!source.Read(offset, count, buffer) || !sink.Write(buffer, count)) {
        *error = "media copy failed"; return false;
      }
      offset += count;
    }
    written += fragment.end - fragment.begin;
  }
  return true;
}
}  // namespace internet_browser
#endif
