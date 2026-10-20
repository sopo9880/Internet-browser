// Internet Browser's own SOCKS5 transport. No system proxy settings are changed.
#include <winsock2.h>

#include "chrome/browser/internet_browser/transport.h"

#include <array>
#include <string>

#include "base/command_line.h"
#include "base/containers/span.h"
#include "base/files/file_util.h"
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
#include "base/win/scoped_handle.h"
#include "chrome/common/chrome_paths.h"

namespace internet_browser {
namespace {
struct State {
  base::Lock lock;
  base::Process process;
  base::win::ScopedHandle job;
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

// An ephemeral loopback port avoids taking over another application's 1080.
int AllocatePort() {
  SOCKET socket_handle = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (socket_handle == INVALID_SOCKET)
    return 0;
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  int port = 0;
  if (bind(socket_handle, reinterpret_cast<sockaddr*>(&address),
           sizeof(address)) == 0) {
    int size = sizeof(address);
    if (getsockname(socket_handle, reinterpret_cast<sockaddr*>(&address),
                    &size) == 0)
      port = ntohs(address.sin_port);
  }
  closesocket(socket_handle);
  return port;
}

bool CheckSocks(int port) {
  SOCKET socket_handle = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (socket_handle == INVALID_SOCKET)
    return false;
  DWORD timeout_ms = 300;
  setsockopt(socket_handle, SOL_SOCKET, SO_RCVTIMEO,
             reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));
  setsockopt(socket_handle, SOL_SOCKET, SO_SNDTIMEO,
             reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));
  sockaddr_in address{};
  address.sin_family = AF_INET;
  address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  address.sin_port = htons(static_cast<u_short>(port));
  const char greeting[] = {5, 1, 0};
  std::array<char, 2> response{};
  bool ok = connect(socket_handle, reinterpret_cast<sockaddr*>(&address),
                    sizeof(address)) == 0 &&
            send(socket_handle, greeting, sizeof(greeting), 0) == sizeof(greeting);
  int count = 0;
  while (ok && count < 2) {
    int read = recv(socket_handle,
                    base::span(response).subspan(static_cast<size_t>(count)).data(),
                    2 - count, 0);
    if (read <= 0) {
      ok = false;
      break;
    }
    count += read;
  }
  closesocket(socket_handle);
  return ok && response[0] == 5 && response[1] == 0;
}
}  // namespace

void StartTransport() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  auto configuration = ReadConfig();
  state.enabled = configuration.FindBool("enabled").value_or(false);
  if (auto* preset = configuration.FindString("preset");
      preset && ValidPreset(*preset))
    state.preset = *preset;
  if (!state.enabled)
    return;
  auto* command_line = base::CommandLine::ForCurrentProcess();
  if (command_line->HasSwitch("proxy-server")) {
    state.status = "명령행 프록시 설정 사용 중 · 내장 ByeDPI 시작하지 않음";
    return;
  }
  WSADATA data{};
  if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
    // Fail closed when the requested transport cannot initialize.
    command_line->AppendSwitchASCII("proxy-server", "socks5://127.0.0.1:1");
    state.status = "네트워크 초기화 실패 · 설정에서 ByeDPI를 끄고 다시 시작하세요.";
    return;
  }
  int port = AllocatePort();
  command_line->AppendSwitchASCII("proxy-server", "socks5://127.0.0.1:" +
                                 base::NumberToString(port ? port : 1));
  command_line->AppendSwitch("disable-quic");
  base::FilePath executable_directory;
  if (!port || !base::PathService::Get(base::DIR_EXE, &executable_directory)) {
    state.status = "ByeDPI 포트 초기화 실패 · 브라우저 프록시 연결을 차단했습니다.";
    WSACleanup();
    return;
  }
  base::CommandLine engine(executable_directory.AppendASCII("tools")
                              .AppendASCII("ciadpi.exe"));
  for (const auto& argument : {"-i", "127.0.0.1", "-p"})
    engine.AppendArg(argument);
  engine.AppendArg(base::NumberToString(port));
  engine.AppendArg("--split");
  engine.AppendArg("1+s");
  if (state.preset == "disorder" || state.preset == "aggressive") {
    engine.AppendArg("--disorder");
    engine.AppendArg("3+s");
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
  state.job.Set(CreateJobObject(nullptr, nullptr));
  JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
  limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
  if (!state.job.IsValid() ||
      !SetInformationJobObject(state.job.get(), JobObjectExtendedLimitInformation,
                               &limits, sizeof(limits))) {
    state.status = "ByeDPI 프로세스 관리 초기화 실패";
    WSACleanup();
    return;
  }
  base::LaunchOptions options;
  options.start_hidden = true;
  options.job_handle = state.job.get();
  state.process = base::LaunchProcess(engine, options);
  for (int attempt = 0; state.process.IsValid() && attempt < 20; ++attempt) {
    if (CheckSocks(port)) {
      state.active = true;
      break;
    }
    base::PlatformThread::Sleep(base::Milliseconds(100));
  }
  state.status = state.active
      ? "로컬 SOCKS5 연결 확인 · 사이트별 우회 효과는 별도 확인 필요"
      : "ByeDPI 시작 실패 · 설정에서 끄고 다시 시작하거나 오류를 확인하세요.";
  WSACleanup();
}

void StopTransport() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  state.job.Close();  // Kill only this browser's owned process tree.
  state.process.Close();
  state.active = false;
}

base::DictValue GetStatus() {
  auto& state = GetState();
  base::AutoLock lock(state.lock);
  auto result = ReadConfig();
  result.Set("active", state.active && state.process.IsRunning());
  result.Set("activePreset", state.preset);
  result.Set("activeEnabled", state.enabled);
  result.Set("status", state.active && !state.process.IsRunning()
      ? "ByeDPI 엔진이 종료되었습니다. 브라우저를 다시 시작하세요."
      : state.status);
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
  bool ok = base::WriteFile(temporary, *contents) &&
            base::ReplaceFile(temporary, path, nullptr);
  if (!ok)
    base::DeleteFile(temporary);
  return ok;
}
}  // namespace internet_browser
