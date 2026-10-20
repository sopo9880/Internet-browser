import {sendWithPromise} from 'chrome://resources/js/cr.js';

const enabled = document.querySelector('#enabled');
const preset = document.querySelector('#preset');
const transportStatus = document.querySelector('#transport-status');
const saveStatus = document.querySelector('#save-status');
const customOptions = document.querySelector('#custom-options');
const customFlags = ['split', 'disorder', 'tlsRecord', 'autoRetry', 'httpModification', 'fakePacket'];
const customPositions = {split: 'splitValue', disorder: 'disorderValue', tlsRecord: 'tlsValue', fakePacket: 'fakeTtl'};
const control = name => document.querySelector(`#custom-${name}`);
function refreshCustomControls() {
  customOptions.hidden = preset.value !== 'custom';
  customOptions.disabled = customOptions.hidden;
  for (const [flag, field] of Object.entries(customPositions)) {
    control(field).disabled = !control(flag).checked;
    control(field).required = control(flag).checked;
  }
}
preset.addEventListener('change', refreshCustomControls);
for (const flag of customFlags) control(flag).addEventListener('change', refreshCustomControls);
try {
  const state = await sendWithPromise('internetBrowserStatus');
  enabled.checked = state.enabled ?? false;
  preset.value = state.preset ?? 'balanced';
  for (const flag of customFlags) {
    if (typeof state.custom?.[flag] === 'boolean') control(flag).checked = state.custom[flag];
  }
  for (const field of Object.values(customPositions)) {
    if (state.custom?.[field] !== undefined) control(field).value = state.custom[field];
  }
  transportStatus.textContent = state.status;
} catch {
  transportStatus.textContent = '연결 상태를 불러오지 못했습니다. 페이지를 다시 열어 주세요.';
}
refreshCustomControls();
document.querySelector('#dpi-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    const custom = Object.fromEntries(customFlags.map(flag => [flag, control(flag).checked]));
    for (const field of Object.values(customPositions)) custom[field] = control(field).value;
    custom.fakeTtl = Number(custom.fakeTtl || 8);
    const result = await sendWithPromise('internetBrowserSave', enabled.checked, preset.value, custom);
    saveStatus.textContent = result.saved
      ? '저장했습니다. 브라우저를 완전히 종료한 뒤 다시 열어 주세요.'
      : '설정을 저장하지 못했습니다.';
  } catch {
    saveStatus.textContent = '설정을 저장하지 못했습니다.';
  } finally {
    button.disabled = false;
  }
});

try {
  const legacy = await sendWithPromise('internetBrowserLegacy');
  document.querySelector('#legacy-section').hidden = !legacy.found;
  for (const name of ['update_auto_check', 'update_last_auto_check', 'update_snoozed_tag', 'update_snoozed_until']) {
    if (localStorage.getItem(name) === null && ['string', 'number', 'boolean'].includes(typeof legacy.settings?.[name]))
      localStorage.setItem(name, String(legacy.settings[name]));
  }
  for (const address of legacy.history ?? []) {
    const url = new URL(address);
    if (!['http:', 'https:'].includes(url.protocol)) continue;
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = url.href;
    link.textContent = url.href;
    item.append(link);
    document.querySelector('#legacy-history').append(item);
  }
} catch {
  document.querySelector('#legacy-section').hidden = false;
  document.querySelector('#import-status').textContent = '이전 데이터를 불러오지 못했습니다. 원본 파일은 보관되어 있습니다.';
}
document.querySelector('#import-bookmarks').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await sendWithPromise('internetBrowserImportBookmarks');
    document.querySelector('#import-status').textContent = result.error ??
      `${result.imported}개의 북마크를 가져왔습니다. 이미 가져온 주소는 중복 추가하지 않습니다.`;
  } catch {
    document.querySelector('#import-status').textContent = '북마크를 가져오지 못했습니다.';
  } finally {
    button.disabled = false;
  }
});
let libraryLoading = false;
async function refreshLibrary() {
if (libraryLoading) return;
libraryLoading = true;
document.querySelector('#refresh-videos').disabled = true;
try {
  const library = await sendWithPromise('internetBrowserVideos');
  if (library.error) throw new Error(library.error);
  document.querySelector('#videos').replaceChildren();
  document.querySelector('#video-status').textContent = library.videos.length
    ? `${library.videos.length}개의 저장된 영상` : '저장된 영상이 없습니다.';
  if (library.privateSession) document.querySelector('#video-status').textContent += ' · 시크릿 창의 재생 기록은 저장하지 않습니다.';
  for (const video of library.videos) {
    const item = document.createElement('li');
    const link = document.createElement('button');
    const url = new URL(video.url);
    if (!['file:', 'content:'].includes(url.protocol)) continue;
    link.className = 'play-video';
    link.dataset.videoUrl = url.href;
    link.textContent = video.title;
    link.addEventListener('click', async () => {
      try {
        const result = await sendWithPromise('internetBrowserOpenVideo', url.href);
        if (!result.opened) document.querySelector('#video-status').textContent = '파일을 찾을 수 없습니다.';
      } catch {
        document.querySelector('#video-status').textContent = '영상을 열지 못했습니다.';
      }
    });
    const rename = document.createElement('button');
    rename.type = 'button'; rename.className = 'secondary rename-video';
    rename.textContent = '이름 변경';
    rename.disabled = library.privateSession === true;
    rename.addEventListener('click', async () => {
      const title = prompt('영상 제목', link.textContent);
      if (title === null) return;
      rename.disabled = true;
      try {
        const result = await sendWithPromise('internetBrowserRenameVideo', url.href, title);
        if (result.saved) {
          link.textContent = result.title;
          document.querySelector('#video-status').textContent = '제목을 저장했습니다.';
        } else document.querySelector('#video-status').textContent = result.error || '제목을 저장하지 못했습니다. 제목과 파일 상태를 확인해 주세요.';
      } catch {document.querySelector('#video-status').textContent = '제목을 저장하지 못했습니다.';}
      finally {rename.disabled = false;}
    });
    item.append(link, document.createTextNode(' '), rename);
    document.querySelector('#videos').append(item);
  }
} catch {
  document.querySelector('#video-status').textContent = '영상 목록을 불러오지 못했습니다. 파일은 원래 위치에 보관되어 있습니다.';
} finally {libraryLoading = false; document.querySelector('#refresh-videos').disabled = false;}
}
document.querySelector('#refresh-videos').addEventListener('click', refreshLibrary);
window.addEventListener('focus', refreshLibrary);
await refreshLibrary();

const updateStatus = document.querySelector('#update-status');
const updateAuto = document.querySelector('#update-auto');
const updateRelease = document.querySelector('#update-release');
const updateCheck = document.querySelector('#update-check');
const updateDownload = document.querySelector('#update-download');
const updateInstall = document.querySelector('#update-install');
const updateSettings = document.querySelector('#update-settings');
let updateCandidate;
updateAuto.checked = localStorage.getItem('update_auto_check') !== 'false';
updateAuto.addEventListener('change', () => localStorage.setItem('update_auto_check', String(updateAuto.checked)));
async function checkUpdate(automatic = false) {
  updateCheck.disabled = true;
  updateStatus.textContent = automatic ? '' : '공식 릴리스를 확인하는 중…';
  updateRelease.hidden = true;
  updateInstall.hidden = true;
  updateDownload.disabled = true;
  try {
    const release = await sendWithPromise('internetBrowserUpdate', 'check');
    if (release.error) throw new Error(release.error);
    localStorage.setItem('update_last_auto_check', String(Date.now()));
    if (!release.available) {updateStatus.textContent = automatic ? '' : '최신 버전을 사용 중입니다.'; return;}
    if (automatic && localStorage.getItem('update_snoozed_tag') === release.tag && Number(localStorage.getItem('update_snoozed_until')) > Date.now()) return;
    updateCandidate = release;
    document.querySelector('#update-title').textContent = `Internet Browser ${release.version}`;
    document.querySelector('#update-notes').textContent = release.description || '';
    document.querySelector('#update-page').href = release.releasePage;
    updateDownload.disabled = !release.canInstall;
    updateSettings.hidden = !release.android;
    updateRelease.hidden = false;
    updateStatus.textContent = release.canInstall ? '새 버전이 있습니다. 다운로드한 파일은 설치 전에 검증합니다.' : '이 버전에는 앱에서 검증할 수 있는 설치 파일이 없습니다. 공식 릴리스를 확인해 주세요.';
  } catch (error) {
    updateStatus.textContent = automatic ? '' : error.message;
  } finally {updateCheck.disabled = false;}
}
updateCheck.addEventListener('click', () => checkUpdate());
updateDownload.addEventListener('click', async () => {
  updateDownload.disabled = true; updateCheck.disabled = true;
  updateStatus.textContent = '업데이트 다운로드 및 검증 중… 이 화면을 닫으면 취소됩니다.';
  try {
    const result = await sendWithPromise('internetBrowserUpdate', 'download');
    if (result.error || !result.verified) throw new Error(result.error || '다운로드 파일을 검증하지 못했습니다.');
    updateInstall.hidden = false;
    updateStatus.textContent = '파일 크기와 SHA-256 검증을 완료했습니다. 설치하려면 아래 버튼을 눌러 주세요.';
  } catch (error) {updateStatus.textContent = error.message; updateDownload.disabled = false;}
  finally {updateCheck.disabled = false;}
});
updateInstall.addEventListener('click', async () => {
  if (!confirm(`Internet Browser ${updateCandidate.version} 설치 프로그램을 여시겠습니까?`)) return;
  updateInstall.disabled = true; updateCheck.disabled = true;
  try {
    const result = await sendWithPromise('internetBrowserUpdate', 'install');
    updateStatus.textContent = result.error || (result.opened ? '설치 화면을 열었습니다. 운영체제의 안내에 따라 진행해 주세요.' : '설치 화면을 열지 못했습니다.');
  } catch {updateStatus.textContent = '설치 화면을 열지 못했습니다.';}
  finally {updateInstall.disabled = false; updateCheck.disabled = false;}
});
updateSettings.addEventListener('click', async () => {
  try {
    const result = await sendWithPromise('internetBrowserUpdate', 'settings');
    if (!result.opened) updateStatus.textContent = '설정을 열지 못했습니다. Android 설정에서 이 앱의 설치 권한을 확인해 주세요.';
  } catch {updateStatus.textContent = '설정 화면을 열지 못했습니다.';}
});
document.querySelector('#update-snooze').addEventListener('click', () => {
  if (!updateCandidate) return;
  localStorage.setItem('update_snoozed_tag', updateCandidate.tag);
  localStorage.setItem('update_snoozed_until', String(Date.now() + 7 * 24 * 60 * 60 * 1000));
  updateRelease.hidden = true;
  updateStatus.textContent = '7일 뒤 다시 알려드리겠습니다. 직접 업데이트 확인은 언제든 가능합니다.';
});
const lastCheck = Number(localStorage.getItem('update_last_auto_check') || 0);
if (updateAuto.checked && (!Number.isFinite(lastCheck) || Date.now() - lastCheck >= 12 * 60 * 60 * 1000)) await checkUpdate(true);
