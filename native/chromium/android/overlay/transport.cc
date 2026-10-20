// Browser-owned Android transport. No VPN or system proxy changes.
#include "chrome/browser/internet_browser/transport.h"

#include <arpa/inet.h>
#include <signal.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <array>
#include <string>

#include "base/android/path_utils.h"
#include "base/command_line.h"
#include "base/containers/span.h"
#include "base/files/file_util.h"
#include "base/files/scoped_file.h"
#include "base/json/json_reader.h"
#include "base/json/json_writer.h"
#include "base/no_destructor.h"
#include "base/path_service.h"
#include "base/process/launch.h"
#include "base/process/process.h"
#include "base/strings/string_number_conversions.h"
#include "base/synchronization/lock.h"
#include "base/threading/platform_thread.h"
#include "base/time/time.h"
#include "chrome/common/chrome_paths.h"

namespace internet_browser {
namespace {
struct State {
  base::Lock lock;
  base::Process process;
  bool active = false;
  bool enabled = false;
  std::string preset = "balanced";
  std::string status = "사용 안 함";
};
State& GetState() {
  static base::NoDestructor<State> state;
  return *state;
}

base::FilePath ConfigPath() {
  base::FilePath root;
  if (!base::PathService::Get(chrome::DIR_USER_DATA, &root))
    return {};
  return root.AppendASCII("internet-browser.json");
}

base::DictValue ReadConfig() {
  std::string data;
  auto path = ConfigPath();
  if (!path.empty() && base::ReadFileToStringWithMaxSize(path, &data, 64 * 1024)) {
    auto value = base::JSONReader::ReadDict(data, base::JSON_PARSE_RFC);
    if (value)
      return std::move(*value);
  }
  return {};
}

bool ValidPreset(const std::string& preset) {
  return preset == "balanced" || preset == "split" ||
         preset == "disorder" || preset == "aggressive";
}

int AllocatePort() {
  base::ScopedFD descriptor(socket(AF_INET, SOCK_STREAM, IPPROTO_TCP));
  if (!descriptor.is_valid())
    return 0;
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(descriptor.get(), reinterpret_cast<sockaddr*>(&address), sizeof(address)))
    return 0;
  socklen_t size = sizeof(address);
  if (getsockname(descriptor.get(), reinterpret_cast<sockaddr*>(&address), &size))
    return 0;
  return ntohs(address.sin_port);
}

bool CheckSocks(int port) {
  base::ScopedFD descriptor(socket(AF_INET, SOCK_STREAM, IPPROTO_TCP));
  if (!descriptor.is_valid())
    return false;
  timeval timeout{0, 300000};
  setsockopt(descriptor.get(), SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
  setsockopt(descriptor.get(), SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = htons(static_cast<uint16_t>(port));
  const char greeting[] = {5, 1, 0};
  std::array<char, 2> response{};
  bool ok = connect(descriptor.get(), reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0 &&
            send(descriptor.get(), greeting, sizeof(greeting), MSG_NOSIGNAL) == static_cast<ssize_t>(sizeof(greeting));
  size_t count = 0;
  while (ok && count < response.size()) {
    auto buffer = base::span(response).subspan(count);
    ssize_t received = recv(descriptor.get(), buffer.data(), buffer.size(), 0);
    if (received <= 0) {
      ok = false;
      break;
    }
    count += static_cast<size_t>(received);
  }
  return ok && response[0] == 5 && response[1] == 0;
}

// Android has no Windows job handle. Arrange a kernel-enforced lifetime for
// this child only, including crashes/OS termination of the browser process.
class ParentLifetime final : public base::LaunchOptions::PreExecDelegate {
 public:
  ParentLifetime() : parent_(getpid()) {}
  void RunAsyncSafe() override {
    if (syscall(SYS_prctl, PR_SET_PDEATHSIG, SIGKILL, 0, 0, 0) != 0 ||
        getppid() != parent_)
      _exit(1);
  }
 private:
  const pid_t parent_;
};
}  // namespace

void StartTransport() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  auto configuration = ReadConfig();
  state.enabled = configuration.FindBool("enabled").value_or(false);
  if (const auto* preset = configuration.FindString("preset"))
    state.preset = *preset;
  if (!state.enabled)
    return;
  auto* command_line = base::CommandLine::ForCurrentProcess();
  if (command_line->HasSwitch("proxy-server")) {
    state.status = "명령행 프록시 설정 사용 중 · 내장 ByeDPI 시작하지 않음";
    return;
  }
  int port = ValidPreset(state.preset) ? AllocatePort() : 0;
  command_line->AppendSwitchASCII("proxy-server", "socks5://127.0.0.1:" +
                                  base::NumberToString(port ? port : 1));
  command_line->AppendSwitch("disable-quic");
  base::FilePath directory;
  if (!port || !base::android::GetNativeLibraryDirectory(&directory)) {
    state.status = "ByeDPI 설정 또는 초기화 오류 · 프록시 연결을 차단했습니다.";
    return;
  }
  base::CommandLine engine(directory.AppendASCII("libciadpi.so"));
  for (const auto* argument : {"-i", "127.0.0.1", "-p"})
    engine.AppendArg(argument);
  engine.AppendArg(base::NumberToString(port));
  engine.AppendArg("--split");
  engine.AppendArg("1+s");
  if (state.preset == "disorder" || state.preset == "aggressive") {
    engine.AppendArg("--disorder");
    engine.AppendArg("1");  // Preserve the existing Android preset.
  }
  if (state.preset == "balanced" || state.preset == "aggressive") {
    engine.AppendArg("--auto");
    engine.AppendArg("torst");
  }
  if (state.preset != "disorder") {
    engine.AppendArg("--tlsrec");
    engine.AppendArg("1+s");
  }
  if (state.preset == "aggressive") {
    engine.AppendArg("--mod-http");
    engine.AppendArg("h,d");
  }
  ParentLifetime lifetime;
  base::LaunchOptions options;
  options.pre_exec_delegate = &lifetime;
  state.process = base::LaunchProcess(engine, options);
  for (int attempt = 0; state.process.IsValid() && attempt < 20; ++attempt) {
    if (!state.process.IsRunning())
      break;
    if (CheckSocks(port)) {
      state.active = true;
      break;
    }
    base::PlatformThread::Sleep(base::Milliseconds(100));
  }
  state.status = state.active
      ? "로컬 SOCKS5 연결 확인 · 사이트별 우회 효과는 별도 확인 필요"
      : "ByeDPI 시작 실패 · 설정에서 끄고 다시 시작하거나 오류를 확인하세요.";
}

void StopTransport() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  if (state.process.IsValid())
    state.process.Terminate(0, false);
  state.process.Close();
  state.active = false;
}

base::DictValue GetStatus() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  if (state.active && !state.process.IsRunning()) {
    state.active = false;
    state.process.Close();
    state.status = "ByeDPI 엔진이 종료되었습니다. 브라우저를 다시 시작하세요.";
  }
  auto result = ReadConfig();
  result.Set("active", state.active);
  result.Set("activePreset", state.preset);
  result.Set("activeEnabled", state.enabled);
  result.Set("status", state.status);
  return result;
}

bool SaveConfiguration(bool enabled, const std::string& preset) {
  if (!ValidPreset(preset))
    return false;
  auto path = ConfigPath();
  if (path.empty() || !base::CreateDirectory(path.DirName()))
    return false;
  base::DictValue configuration;
  configuration.Set("enabled", enabled);
  configuration.Set("preset", preset);
  auto contents = base::WriteJson(configuration);
  if (!contents)
    return false;
  base::FilePath temporary;
  if (!base::CreateTemporaryFileInDir(path.DirName(), &temporary))
    return false;
  bool ok = base::WriteFile(temporary, *contents) && base::ReplaceFile(temporary, path, nullptr);
  if (!ok)
    base::DeleteFile(temporary);
  return ok;
}
}  // namespace internet_browser
