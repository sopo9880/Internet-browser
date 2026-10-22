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

const captureStatus = document.querySelector('#capture-status');
function videoSizeLabel(item) {
  let amount = item.sizeBytes;
  if (!Number.isFinite(amount) || amount <= 0 || amount > Number.MAX_SAFE_INTEGER) return '용량 미확인';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; ++unit; }
  const text = amount.toLocaleString('ko-KR', {maximumFractionDigits: unit ? 1 : 0});
  return `${item.sizeEstimated ? '약 ' : ''}${text} ${units[unit]}`;
}
const scanButton = document.querySelector('#scan-videos');
scanButton.addEventListener('click', async () => {
  scanButton.disabled = true;
  captureStatus.textContent = '열린 페이지에서 영상을 찾고 있습니다…';
  document.querySelector('#capture-results').replaceChildren();
  document.querySelector('#capture-reasons').replaceChildren();
  try {
    const result = await sendWithPromise('internetBrowserCapture', 'scan');
    if (result.error) throw new Error(result.error);
    const groups = new Map();
    for (const item of result.items || []) {
      if (!groups.has(item.page)) groups.set(item.page, []);
      groups.get(item.page).push(item);
    }
    captureStatus.textContent = result.items.length ? `${result.items.length}개의 저장 후보를 찾았습니다.`
      : '저장 가능한 영상 파일을 찾지 못했습니다. 원본 탭에서 영상을 재생한 뒤 다시 검사하세요.';
    if (result.partial) captureStatus.textContent += ' 응답하지 않는 일부 페이지는 제외했습니다.';
    for (const reason of result.reasons || []) {
      const li = document.createElement('li'); li.textContent = reason;
      document.querySelector('#capture-reasons').append(li);
    }
    for (const [page, items] of groups) {
      const row = document.createElement('article');
      const description = document.createElement('div');
      const heading = document.createElement('h3'); heading.textContent = items[0].title || '영상';
      const source = document.createElement('p'); source.className = 'muted';
      try { source.textContent = new URL(page).hostname; } catch { source.textContent = '열린 페이지'; }
      const select = document.createElement('select'); select.setAttribute('aria-label', '저장할 영상과 화질');
      for (const [index, item] of items.entries()) {
        const option = document.createElement('option'); option.value = String(index);
        option.textContent = `${item.quality || '원본 화질'} · ${videoSizeLabel(item)} · ${item.paired ? '영상+음성 함께 저장' : item.convertedFromTs ? 'MPEG-TS → MP4' : item.kind === 'stream' ? '저장 가능한 MP4 스트림' : item.kind === 'file' ? (item.mime || '영상 파일') : ['youtube', 'youtube_hls'].includes(item.kind) ? 'YouTube 영상' : item.kind.toUpperCase()} · ${index + 1}`;
        select.append(option);
      }
      const save = document.createElement('button'); save.textContent = '영상 저장';
      const updateSaveLabel = () => {
        const kind = items[Number(select.value)].kind;
        save.textContent = kind === 'youtube' ? '화질 가져오기' : ['hls', 'dash'].includes(kind) ? '스트림 확인' : '영상 저장';
      };
      select.addEventListener('change', updateSaveLabel); updateSaveLabel();
      save.addEventListener('click', async () => {
        save.disabled = true;
        try {
          const selected = items[Number(select.value)];
          if (['hls', 'dash', 'youtube', 'youtube_hls'].includes(selected.kind)) {
            captureStatus.textContent = '스트림 형식과 제공 화질을 확인하고 있습니다…';
            const response = await sendWithPromise('internetBrowserCapture', 'inspect', selected.token);
            if (response.error) throw new Error(response.error);
            if (selected.kind === 'youtube_hls') {
              const ready = response.items?.find(item => item.kind === 'stream');
              if (!ready) throw new Error('이 화질의 영상과 음성을 준비하지 못했습니다. 화질을 다시 가져와 주세요.');
              const download = await sendWithPromise('internetBrowserCapture', 'download', ready.token);
              captureStatus.textContent = download.error || (download.started ? '다운로드를 시작했습니다. 완료되면 서재에 표시됩니다.' : '다운로드를 시작하지 못했습니다.');
              await refreshTransfers();
              return;
            }
            for (const item of response.items || []) {
              const index = items.length; items.push(item);
              const option = document.createElement('option'); option.value = String(index);
              option.textContent = `${item.quality || '원본 화질'} · ${videoSizeLabel(item)} · ${item.paired ? '영상+음성 함께 저장' : item.convertedFromTs ? 'MPEG-TS → MP4' : item.kind === 'stream' ? '저장 가능한 MP4 스트림' : 'HLS 화질 선택'}${item.audioLanguage ? ` · 음성 ${item.audioLanguage}` : ''}`;
              select.append(option);
            }
            if (response.items?.length) {
              select.value = String(items.length - response.items.length); updateSaveLabel();
              captureStatus.textContent = response.items.some(item => ['stream', 'youtube_hls'].includes(item.kind)) ? '화질을 선택한 뒤 영상 저장을 눌러 주세요.' : '제공 화질을 선택한 뒤 스트림 확인을 눌러 주세요.';
            } else captureStatus.textContent = '저장 가능한 스트림을 찾지 못했습니다.';
            return;
          }
          const response = await sendWithPromise('internetBrowserCapture', 'download', selected.token);
          captureStatus.textContent = response.error || (response.started ? '다운로드를 시작했습니다. 완료되면 서재에 표시됩니다.' : '다운로드를 시작하지 못했습니다.');
          await refreshTransfers();
        } catch (error) { captureStatus.textContent = error.message || '다운로드를 시작하지 못했습니다. 다시 검사해 주세요.'; }
        finally { save.disabled = false; }
      });
      description.append(heading, source, select); row.append(description, save);
      document.querySelector('#capture-results').append(row);
    }
  } catch (error) { captureStatus.textContent = error.message || '영상을 검사하지 못했습니다.'; }
  finally { scanButton.disabled = false; }
});
let transfersLoading = false;
let transferSummary = '';
async function refreshTransfers() {
  if (transfersLoading || document.hidden) return;
  transfersLoading = true;
  try {
    const result = await sendWithPromise('internetBrowserCapture', 'transfers');
    if (result.error) throw new Error(result.error);
    const summary = JSON.stringify(result.items.map(item => [item.guid, item.state, item.paused]));
    if (transferSummary && summary !== transferSummary) await refreshLibrary();
    transferSummary = summary;
    const container = document.querySelector('#video-transfers'); container.replaceChildren();
    for (const item of result.items) {
      const row = document.createElement('div'); row.className = 'video-transfer';
      const text = document.createElement('p');
      const states = ['다운로드 중', '완료', '취소됨', '중단됨'];
      const state = item.blocked ? '브라우저의 안전 확인이 필요합니다. 전체 다운로드에서 확인하세요.'
        : item.pausing ? '현재 구간을 마친 뒤 일시정지' : item.paused ? '일시정지' : states[item.state] || '상태 확인 중';
      const amount = `${(item.received / 1048576).toFixed(1)} MB`;
      text.textContent = `${item.name} · ${state} · ${amount}${item.stream ? ` · ${item.completedParts}/${item.totalParts} 구간` : ''}${item.error ? ` · ${item.error}` : ''}`;
      row.append(text);
      if (item.total > 0) {
        const progress = document.createElement('progress'); progress.max = item.total; progress.value = item.received;
        progress.setAttribute('aria-label', `${item.name} 다운로드 진행률`); row.append(progress);
      }
      for (const [action, label, visible] of [
        ['pause', '일시정지', item.state === 0 && !item.paused],
        ['resume', '재개', item.canResume], ['cancel', '취소', item.state === 0]
      ]) {
        if (!visible || item.blocked) continue;
        const button = document.createElement('button'); button.className = 'secondary'; button.textContent = label;
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            const response = await sendWithPromise('internetBrowserCapture', 'control', item.guid, action);
            if (response.error) captureStatus.textContent = response.error;
          } catch { captureStatus.textContent = '다운로드 상태를 변경하지 못했습니다.'; }
          finally { await refreshTransfers(); }
        });
        row.append(button);
      }
      container.append(row);
    }
    if (!result.items.length) container.textContent = '진행 중인 영상 다운로드가 없습니다.';
  } catch { document.querySelector('#video-transfers').textContent = '다운로드 상태를 불러오지 못했습니다.'; }
  finally { transfersLoading = false; }
}
await refreshTransfers();
setInterval(refreshTransfers, 1500);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshTransfers(); });

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
