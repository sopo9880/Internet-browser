#include "chrome/browser/internet_browser/updater.h"
#include <array>
#include <memory>
#include <utility>
#include "base/command_line.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/functional/bind.h"
#include "base/json/json_reader.h"
#include "base/process/launch.h"
#include "base/strings/string_number_conversions.h"
#include "base/task/thread_pool.h"
#include "base/time/time.h"
#include "build/build_config.h"
#include "chrome/browser/internet_browser/resources.h"
#include "chrome/browser/internet_browser/update_manifest.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/platform_util.h"
#include "content/public/browser/storage_partition.h"
#include "crypto/hash.h"
#include "net/base/load_flags.h"
#include "net/traffic_annotation/network_traffic_annotation.h"
#include "services/network/public/cpp/resource_request.h"
#include "services/network/public/cpp/shared_url_loader_factory.h"
#include "services/network/public/cpp/simple_url_loader.h"
#include "services/network/public/mojom/url_response_head.mojom.h"
#include "net/http/http_response_headers.h"
#if BUILDFLAG(IS_ANDROID)
#include "base/android/jni_android.h"
#include "base/android/jni_string.h"
#include "chrome/browser/util/jni_headers/PlatformUtil_jni.h"
#endif


namespace internet_browser {
namespace {
constexpr char kLatest[] = "https://api.github.com/repos/sopo9880/Internet-browser/releases/latest";
constexpr auto kTraffic = net::DefineNetworkTrafficAnnotation("internet_browser_product_update", R"(
  semantics {
    sender: "Internet Browser product updater"
    description: "Checks this product's public GitHub release and downloads an explicitly selected installer."
    trigger: "Opening the product hub or requesting an update. Installer download and execution require user actions."
    data: "A public release request and selected public asset URL; no account credentials or cookies."
    destination: WEBSITE
  }
  policy {
    cookies_allowed: NO
    setting: "The user controls update checks in the product hub."
    policy_exception_justification: "This independent product has no enterprise update policy."
  }
)");
base::DictValue Error(const char* message) {
  base::DictValue result;
  result.Set("error", message);
  return result;
}
std::unique_ptr<network::SimpleURLLoader> Loader(const GURL& url) {
  auto request = std::make_unique<network::ResourceRequest>();
  request->url = url;
  request->credentials_mode = network::mojom::CredentialsMode::kOmit;
  request->load_flags = net::LOAD_DISABLE_CACHE;
  request->upgrade_if_insecure = true;
  request->headers.SetHeader("Accept", "application/vnd.github+json");
  request->headers.SetHeader("User-Agent", "Internet-Browser-Update-Checker");
  auto loader = network::SimpleURLLoader::Create(std::move(request), kTraffic);
  loader->SetTimeoutDuration(base::Minutes(5));
  return loader;
}
base::FilePath CreateUpdateDirectory(base::FilePath profile) {
#if BUILDFLAG(IS_ANDROID)
  const base::FilePath parent(Java_PlatformUtil_getInternetBrowserUpdateDirectory(
      base::android::AttachCurrentThread()));
#else
  const auto parent = profile.AppendASCII("InternetBrowserUpdates");
#endif
  base::FilePath directory;
  if (!base::CreateDirectory(parent) ||
      !base::CreateTemporaryDirInDir(parent, FILE_PATH_LITERAL("update-"), &directory))
    return {};
  return directory;
}
bool VerifyInstaller(const base::FilePath& path, const base::DictValue& installer) {
  const auto size = installer.FindInt("size");
  const auto* expected = installer.FindString("sha256");
  if (!size || !expected || base::IsLink(path)) return false;
  base::File file(path, base::File::FLAG_OPEN | base::File::FLAG_READ);
  std::array<uint8_t, crypto::hash::kSha256Size> digest;
  return file.IsValid() && file.GetLength() == *size &&
      crypto::hash::HashFile(crypto::hash::kSha256, &file, digest) &&
      base::HexEncodeLower(digest) == *expected;
}
base::FilePath FinalizeInstaller(base::FilePath partial, base::DictValue installer) {
  const auto* name = installer.FindString("name");
  if (partial.empty() || !name || !VerifyInstaller(partial, installer)) {
    if (!partial.empty()) base::DeleteFile(partial);
    return {};
  }
  const auto target = partial.DirName().AppendASCII(*name);
  if (!base::Move(partial, target)) return {};
  return target;
}
}  // namespace
NativeUpdater::NativeUpdater(Profile* profile) : profile_(profile) {}
NativeUpdater* NativeUpdater::Get(Profile* profile) {
  static constexpr char key[] = "internet-browser-updater";
  auto* updater = static_cast<NativeUpdater*>(profile->GetUserData(key));
  if (!updater) {
    auto owned = std::make_unique<NativeUpdater>(profile); updater = owned.get();
    profile->SetUserData(key, std::move(owned));
  }
  return updater;
}
NativeUpdater::~NativeUpdater() {
  loader_.reset();
  if (!keep_installer_ && !directory_.empty())
    base::ThreadPool::PostTask(FROM_HERE, {base::MayBlock()},
        base::BindOnce([](base::FilePath directory) {base::DeletePathRecursively(directory);}, directory_));
}
void NativeUpdater::Check(Reply reply) {
  if (busy_) {std::move(reply).Run(Error("다른 업데이트 작업이 진행 중입니다.")); return;}
  busy_ = true;
  loader_ = Loader(GURL(kLatest));
  loader_->SetTimeoutDuration(base::Seconds(20));
  loader_->DownloadToString(profile_->GetDefaultStoragePartition()->GetURLLoaderFactoryForBrowserProcess().get(),
      base::BindOnce(&NativeUpdater::ManifestReceived, weak_factory_.GetWeakPtr(), std::move(reply)), 1024 * 1024);
}
void NativeUpdater::ManifestReceived(Reply reply, std::optional<std::string> body) {
  const auto* response = loader_->ResponseInfo();
  const bool not_found = response && response->headers && response->headers->response_code() == 404;
  loader_.reset();
  busy_ = false;
  if (not_found) {
    base::DictValue result;result.Set("available", false);std::move(reply).Run(std::move(result));return;
  }
  auto manifest = body ? base::JSONReader::ReadDict(*body, base::JSON_PARSE_RFC) : std::nullopt;
  if (!manifest) {std::move(reply).Run(Error("공식 릴리스 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."));return;}
  auto next = ParseUpdateManifest(*manifest, kAppVersion, BUILDFLAG(IS_ANDROID));
  const auto* previous = release_.FindDict("installer");
  const auto* incoming = next.FindDict("installer");
  if (!previous || !incoming || previous->FindString("sha256") == nullptr ||
      incoming->FindString("sha256") == nullptr ||
      *previous->FindString("sha256") != *incoming->FindString("sha256")) {
    verified_file_.clear(); phase_ = "idle";
  }
  release_ = std::move(next);
  release_.Set("android", BUILDFLAG(IS_ANDROID));
  std::move(reply).Run(release_.Clone());
}
void NativeUpdater::Download(Reply reply) {
  const auto* installer = release_.FindDict("installer");
  if (busy_ || !installer) {std::move(reply).Run(Error("먼저 설치 가능한 공식 업데이트를 확인해 주세요."));return;}
  if (!verified_file_.empty()) {
    base::DictValue result; result.Set("verified", true); std::move(reply).Run(std::move(result)); return;
  }
  busy_ = true;
  received_bytes_ = 0;
  phase_ = "downloading";
  verified_file_.clear();
  base::ThreadPool::PostTaskAndReplyWithResult(FROM_HERE, {base::MayBlock()},
      base::BindOnce(&CreateUpdateDirectory, profile_->GetPath()),
      base::BindOnce(&NativeUpdater::DownloadDirectoryReady, weak_factory_.GetWeakPtr(), std::move(reply)));
}
void NativeUpdater::DownloadDirectoryReady(Reply reply, base::FilePath directory) {
  if (directory.empty()) {busy_ = false;phase_ = "failed";std::move(reply).Run(Error("업데이트 저장 폴더를 만들지 못했습니다."));return;}
  if (!keep_installer_ && !directory_.empty())
    base::ThreadPool::PostTask(FROM_HERE, {base::MayBlock()},
        base::BindOnce([](base::FilePath old) {base::DeletePathRecursively(old);}, directory_));
  directory_ = directory;
  keep_installer_ = false;
  const auto* installer = release_.FindDict("installer");
  loader_ = Loader(GURL(*installer->FindString("url")));
  loader_->SetOnDownloadProgressCallback(base::BindRepeating(
      [](base::WeakPtr<NativeUpdater> self, uint64_t received) {
        if (self) self->received_bytes_ = received;
      }, weak_factory_.GetWeakPtr()));
  loader_->DownloadToFile(profile_->GetDefaultStoragePartition()->GetURLLoaderFactoryForBrowserProcess().get(),
      base::BindOnce(&NativeUpdater::Downloaded, weak_factory_.GetWeakPtr(), std::move(reply)),
      directory.AppendASCII("installer.part"), *installer->FindInt("size"));
}
void NativeUpdater::Downloaded(Reply reply, base::FilePath file) {
  loader_.reset();
  phase_ = file.empty() ? "failed" : "verifying";
  if (file.empty()) {busy_ = false;std::move(reply).Run(Error("업데이트 다운로드에 실패했습니다. 설치를 실행하지 않았습니다."));return;}
  base::ThreadPool::PostTaskAndReplyWithResult(FROM_HERE, {base::MayBlock()},
      base::BindOnce(&FinalizeInstaller, file, release_.FindDict("installer")->Clone()),
      base::BindOnce(&NativeUpdater::Verified, weak_factory_.GetWeakPtr(), std::move(reply)));
}
void NativeUpdater::Verified(Reply reply, base::FilePath file) {
  busy_ = false;
  verified_file_ = file;
  phase_ = file.empty() ? "failed" : "ready";
  if (!file.empty()) keep_installer_ = true;
  if (file.empty()) {std::move(reply).Run(Error("파일 크기 또는 SHA-256이 일치하지 않아 설치를 중단했습니다."));return;}
  base::DictValue result;result.Set("verified", true);std::move(reply).Run(std::move(result));
}
void NativeUpdater::OpenVerifiedInstaller(Reply reply) {
  const auto* installer = release_.FindDict("installer");
  if (busy_ || verified_file_.empty() || !installer) {std::move(reply).Run(Error("검증된 설치 파일이 없습니다."));return;}
  busy_ = true;
  base::ThreadPool::PostTaskAndReplyWithResult(FROM_HERE, {base::MayBlock()},
      base::BindOnce([](base::FilePath file, base::DictValue installer) {
        if (!VerifyInstaller(file, installer)) return false;
#if BUILDFLAG(IS_WIN)
        return base::LaunchProcess(base::CommandLine(file), base::LaunchOptions()).IsValid();
#elif BUILDFLAG(IS_ANDROID)
        return Java_PlatformUtil_openInternetBrowserInstaller(
            base::android::AttachCurrentThread(), file.value());
#else
        return false;
#endif
      }, verified_file_, installer->Clone()),
      base::BindOnce([](base::WeakPtr<NativeUpdater> self, Reply reply, bool opened) {
        if (!self) return;
        self->busy_ = false;
        self->keep_installer_ = opened;
        base::DictValue result;
        if (opened) result.Set("opened", true);
        else result.Set("error", "설치 프로그램을 열지 못했습니다. 파일 검증 또는 운영체제의 설치 제한을 확인해 주세요.");
        std::move(reply).Run(std::move(result));
      }, weak_factory_.GetWeakPtr(), std::move(reply)));
}
bool NativeUpdater::OpenInstallSettings() {
#if BUILDFLAG(IS_ANDROID)
  return Java_PlatformUtil_openInternetBrowserInstallSettings(base::android::AttachCurrentThread());
#else
  return false;
#endif
}
bool NativeUpdater::OpenSecuritySettings() {
#if BUILDFLAG(IS_ANDROID)
  return Java_PlatformUtil_openInternetBrowserSecuritySettings(base::android::AttachCurrentThread());
#else
  return false;
#endif
}
void NativeUpdater::OpenDownloadLocation(Reply reply) {
  if (verified_file_.empty()) {
    std::move(reply).Run(Error("검증된 설치 파일이 없습니다.")); return;
  }
#if BUILDFLAG(IS_ANDROID)
  base::ThreadPool::PostTaskAndReplyWithResult(FROM_HERE, {base::MayBlock()},
      base::BindOnce([](base::FilePath file, base::DictValue installer) {
        return VerifyInstaller(file, installer) && Java_PlatformUtil_showInternetBrowserUpdateFile(
            base::android::AttachCurrentThread(), file.value());
      }, verified_file_, release_.FindDict("installer")->Clone()),
      base::BindOnce([](Reply reply, bool opened) {
        base::DictValue result; result.Set("opened", opened); std::move(reply).Run(std::move(result));
      }, std::move(reply)));
#else
  platform_util::ShowItemInFolder(profile_, verified_file_);
  base::DictValue result; result.Set("opened", true); std::move(reply).Run(std::move(result));
#endif
}
base::DictValue NativeUpdater::Progress() const {
  auto result = release_.Clone();
  result.Set("phase", phase_);
  result.Set("receivedBytes", static_cast<double>(received_bytes_));
  const auto* installer = release_.FindDict("installer");
  result.Set("totalBytes", installer ? installer->FindInt("size").value_or(0) : 0);
  result.Set("verified", !verified_file_.empty());
  if (!verified_file_.empty()) result.Set("fileName", verified_file_.BaseName().AsUTF8Unsafe());
  return result;
}
}  // namespace internet_browser
