#include "video_playlist.h"
#include <utility>

namespace internet_browser {
VideoPlaylistPart::VideoPlaylistPart(std::string location, std::string label)
    : address(std::move(location)), quality(std::move(label)) {}
VideoPlaylistPart::VideoPlaylistPart(const VideoPlaylistPart&) = default;
VideoPlaylistPart& VideoPlaylistPart::operator=(const VideoPlaylistPart&) = default;
VideoPlaylistPart::VideoPlaylistPart(VideoPlaylistPart&&) noexcept = default;
VideoPlaylistPart& VideoPlaylistPart::operator=(VideoPlaylistPart&&) noexcept = default;
VideoPlaylistPart::~VideoPlaylistPart() = default;
}
