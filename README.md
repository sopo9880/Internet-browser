# Internet Browser

Windows·Android용 개인 브라우저입니다. 소스에서 빌드한 Chromium 위에
DPI 우회(ByeDPI), 영상 찾기·저장·오프라인 재생, 자체 업데이트를 얹습니다.

- 현재 제품 버전: **v0.2.5** (`pubspec.yaml`, `native/chromium/product.json`)
- 엔진: Chromium **155.0.8059.84** (리비전과 depot_tools SHA 고정)
  - Windows: Chromium 본체(`chrome`, `mini_installer`)를 직접 빌드합니다.
  - Android: Titanium/Vanadium 기반 Chromium 포크를 빌드합니다.
- 릴리스 노트: [`docs/releases/`](docs/releases/)

## 구조

| 경로 | 내용 |
|---|---|
| `native/chromium/common/overlay/` | 두 플랫폼 공통 C++ 오버레이: 업데이터, 영상 감지·HLS·DASH·YouTube·자막·저장, DPI 설정 |
| `native/chromium/windows/` | `chrome://internet-browser/` WebUI, ByeDPI 프로세스 관리, 레거시 데이터 이전, GN 인자 |
| `native/chromium/android/` | 설정 Activity, JNI 연동, Flutter 시절 데이터 이전 |
| `tool/chromium/` | Chromium 소스 준비, 오버레이와 패치 적용, 빌드, 서명, 패키징 |
| `tool/tests/` | Python 도구 테스트, 단독 C++/Java 검사, Node 영상 테스트 |
| `lib/`, `test/` | **레거시** Flutter 앱(v0.2.1까지 배포). 네이티브 앱이 이 앱의 저장 데이터를 이전하므로 호환 회귀 빌드로 유지합니다. |
| `third_party/` | mux.js(HLS→MP4 변환), ByeDPI, 라이선스 고지 |

## 검사 실행

Flutter, Chromium 체크아웃, 기기 없이 돌릴 수 있는 검사는 한 명령으로 실행됩니다.
CI도 같은 스크립트를 씁니다. 필요한 도구는 Python 3, JDK, C++20 컴파일러, Node 22입니다.

```bash
tool/run_checks.sh
```

C++ 검사를 AddressSanitizer/UBSan과 함께 돌리려면 다음과 같이 실행합니다.

```bash
SANITIZE=1 tool/run_checks.sh
```

레거시 Flutter 앱 검사(Flutter 3.35.7):

```bash
flutter create --project-name=internet_browser --org=io.github.sopo9880 --platforms=android,windows . \
  && git checkout -- test/widget_test.dart \
  && python3 tool/prepare_platforms.py && flutter pub get && flutter analyze && flutter test
```

## 네이티브 빌드

Chromium 빌드는 RAM 32GB 이상, 디스크 120GB 이상인 전용 러너에서만 현실적입니다.
CI는 `chromium-windows-v022`, `chromium-wsl2` 레이블의 셀프호스트 러너를 씁니다.

- Windows: `tool/chromium/build_windows.py --workspace … --stage …`. 실제 호출은 `.github/workflows/ci.yml`에 있고, 자세한 내용은 [`docs/NATIVE_CHROMIUM_V022.md`](docs/NATIVE_CHROMIUM_V022.md)를 참고하세요.
- Android: `tool/chromium/build_native_android.py --workspace … --stage … --version-code …`. 실제 호출은 `.github/workflows/native-android.yml`에 있고, 자세한 내용은 [`docs/CHROMIUM_NATIVE_BUILD.md`](docs/CHROMIUM_NATIVE_BUILD.md)를 참고하세요.
- 소스 재구성 정보: [`docs/NATIVE_SOURCE_RECONSTRUCTION.md`](docs/NATIVE_SOURCE_RECONSTRUCTION.md)

## 릴리스와 검증 원칙

- PR CI는 릴리스 서명 비밀값을 쓰지 않습니다.
- 네이티브 릴리스는 서명과 스테이징(`native-release-stage.yml`)을 거쳐 정식 빌드 산출물을 재빌드 없이 재사용합니다.
- `release.yml`(Flutter 경로)은 v0.2.1 전용으로 잠겨 있습니다.
- 앱 내 업데이트는 이 저장소의 GitHub 릴리스에서 정확한 파일 이름, URL, 크기, SHA-256이 모두 일치하는 설치 파일만 받습니다. 설치 직전에 한 번 더 검증합니다. 자세한 내용은 [`docs/UPDATES.md`](docs/UPDATES.md)를 참고하세요.
- **컴파일 성공은 기기 검증이 아닙니다.** 실기기 설치, AdBlock(`gighmmpiobklfepjocnamgkkbiglidom`)의 실제 차단, DPI 우회는 별도로 확인해 릴리스 노트에 기록합니다. 절차는 [`docs/POST_RELEASE_ANDROID_VALIDATION.md`](docs/POST_RELEASE_ANDROID_VALIDATION.md)를 참고하세요.
- 영상 저장은 암호화되거나 보호된 스트림(DRM, HLS 키, DASH ContentProtection)을 거부합니다. 권한이 있는 콘텐츠만 저장하세요.

## 문서

- [`docs/DPI_AND_MEDIA.md`](docs/DPI_AND_MEDIA.md): ByeDPI와 영상 기능
- [`docs/ANDROID_CHROMIUM_EXTENSIONS.md`](docs/ANDROID_CHROMIUM_EXTENSIONS.md): Android 확장 지원 기준
- [`docs/ANDROID_V022_INSTALL_BLOCK.md`](docs/ANDROID_V022_INSTALL_BLOCK.md): Samsung 설치 차단 조사
- [`docs/ROADMAP.md`](docs/ROADMAP.md): 로드맵
- [`docs/HISTORY.md`](docs/HISTORY.md): v0.1.x–v0.2.2 개발 이력(이전 README 원문)
