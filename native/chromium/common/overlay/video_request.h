#ifndef CHROME_BROWSER_INTERNET_BROWSER_VIDEO_REQUEST_H_
#define CHROME_BROWSER_INTERNET_BROWSER_VIDEO_REQUEST_H_
#include <optional>
#include <string>
#include "base/strings/string_util.h"
#include "components/download/public/common/download_url_parameters.h"
#include "content/public/browser/render_frame_host.h"
#include "content/public/common/referrer.h"
#include "services/network/public/cpp/header_util.h"
#include "services/network/public/mojom/url_response_head.mojom.h"

namespace internet_browser {
// Retain the genuine source page for ordinary hotlink checks. Never fabricate a
// third-party referrer, expand beyond strict-origin-when-cross-origin, or loosen
// an explicit header/meta policy. The download delegate still performs checks.
// The source page's header policy, captured while the page is still open so
// later parts can keep the same referrer after the user leaves the page.
inline std::optional<network::mojom::ReferrerPolicy> VideoHeaderReferrerPolicy(content::RenderFrameHost* frame) {
  if (const auto* response = frame->GetLastResponseHead(); response && response->headers)
    return network::ParseReferrerPolicy(*response->headers);
  return std::nullopt;
}
inline void SetVideoReferrer(const GURL& source, std::optional<network::mojom::ReferrerPolicy> header_policy,
                             const GURL& target, const std::string& meta_policy,
                             download::DownloadUrlParameters* parameters) {
  using Policy = network::mojom::ReferrerPolicy;
  auto referrer = content::Referrer::SanitizeForRequest(target, {source, Policy::kStrictOriginWhenCrossOrigin});
  bool same_origin = false, origin_only = false;
  const auto tighten = [&](Policy policy) {
    const auto candidate = content::Referrer::SanitizeForRequest(target, {source, policy});
    if (candidate.url.spec().size() < referrer.url.spec().size()) referrer = candidate;
    same_origin |= policy == Policy::kSameOrigin;
    origin_only |= policy == Policy::kOrigin || policy == Policy::kStrictOrigin;
  };
  if (header_policy) tighten(*header_policy);
  const auto meta = base::ToLowerASCII(meta_policy);
  if (meta == "no-referrer" || meta == "never") tighten(Policy::kNever);
  else if (meta == "same-origin") tighten(Policy::kSameOrigin);
  else if (meta == "origin") tighten(Policy::kOrigin);
  else if (meta == "strict-origin") tighten(Policy::kStrictOrigin);
  parameters->set_referrer(referrer.url);
  parameters->set_referrer_policy(referrer.url.is_empty() ? net::ReferrerPolicy::NO_REFERRER
      : same_origin ? net::ReferrerPolicy::CLEAR_ON_TRANSITION_CROSS_ORIGIN
      : origin_only ? net::ReferrerPolicy::ORIGIN_CLEAR_ON_TRANSITION_FROM_SECURE_TO_INSECURE
      : net::ReferrerPolicy::REDUCE_GRANULARITY_ON_TRANSITION_CROSS_ORIGIN);
}
inline void SetVideoReferrer(content::RenderFrameHost* frame, const GURL& target,
                             const std::string& meta_policy,
                             download::DownloadUrlParameters* parameters) {
  SetVideoReferrer(frame->GetLastCommittedURL(), VideoHeaderReferrerPolicy(frame), target, meta_policy, parameters);
}
}
#endif
