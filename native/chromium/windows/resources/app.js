import {sendWithPromise} from 'chrome://resources/js/cr.js';

const settingsTabs = [...document.querySelectorAll('[data-settings-tab]')];
function showSettingsPanel(name, focus = false) {
  if (!settingsTabs.some(tab => tab.dataset.settingsTab === name)) name = 'general';
  for (const tab of settingsTabs) {
    const selected = tab.dataset.settingsTab === name;
    tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  }
  for (const panel of document.querySelectorAll('[data-settings-panel]'))
    panel.hidden = panel.dataset.settingsPanel !== name;
  history.replaceState(null, '', `#${name}`);
}
for (const [index, tab] of settingsTabs.entries()) {
  tab.addEventListener('click', () => showSettingsPanel(tab.dataset.settingsTab));
  tab.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % settingsTabs.length;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index + settingsTabs.length - 1) % settingsTabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = settingsTabs.length - 1;
    if (next !== undefined) { event.preventDefault(); showSettingsPanel(settingsTabs[next].dataset.settingsTab, true); }
  });
}
showSettingsPanel(location.hash.slice(1));
window.addEventListener('hashchange', () => showSettingsPanel(location.hash.slice(1)));

// HTML dialogs work in both the independent Android settings surface and the
// desktop settings window; they don't require a browsing Tab's dialog manager.
function settingsDialog(message, initialText = null) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    const form = document.createElement('form'); form.method = 'dialog'; form.style.display = 'block';
    const text = document.createElement('p'); text.textContent = message; form.append(text);
    let input;
    if (initialText !== null) {
      input = document.createElement('input'); input.type = 'text'; input.value = initialText;
      input.maxLength = 180; input.setAttribute('aria-label', '영상 제목'); form.append(input);
    }
    const buttons = document.createElement('div'); buttons.className = 'dialog-buttons';
    for (const [label, value] of [['취소', 'cancel'], ['확인', 'accept']]) {
      const button = document.createElement('button'); button.textContent = label; button.value = value;
      if (value === 'cancel') button.className = 'secondary'; buttons.append(button);
    }
    form.append(buttons); dialog.append(form); document.body.append(dialog);
    dialog.addEventListener('close', () => {
      const accepted = dialog.returnValue === 'accept'; const value = input?.value;
      dialog.remove(); resolve(initialText === null ? accepted : accepted ? value : null);
    }, {once: true});
    dialog.showModal();
  });
}

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

const blockExternalApps = document.querySelector('#block-external-apps');
try {
  const navigation = await sendWithPromise('internetBrowserNavigation');
  document.querySelector('#navigation-section').hidden = !navigation.supported;
  blockExternalApps.checked = navigation.blockExternalApps === true;
} catch { /* Desktop and unavailable mobile preferences keep the section hidden. */ }
blockExternalApps.addEventListener('change', async () => {
  blockExternalApps.disabled = true;
  const status = document.querySelector('#navigation-status');
  try {
    const result = await sendWithPromise('internetBrowserNavigation', blockExternalApps.checked);
    if (!result.supported) throw new Error('Unsupported navigation setting');
    blockExternalApps.checked = result.blockExternalApps === true;
    status.textContent = '저장했습니다. 다음 링크부터 적용됩니다.';
  } catch {
    blockExternalApps.checked = !blockExternalApps.checked;
    status.textContent = '설정을 저장하지 못했습니다.';
  } finally { blockExternalApps.disabled = false; }
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
let deletingVideos = false;
const selectedVideos = new Map();
async function deleteLibraryVideos(videos, deleteFiles) {
  if (deletingVideos || !videos.length) return;
  const total = videos.reduce((sum, video) => sum + (video.sizeBytes || 0), 0);
  const names = videos.slice(0, 8).map(video => video.title).join('\n');
  if (!await settingsDialog(`${deleteFiles ? '실제 영상 파일을 삭제합니다. 되돌릴 수 없습니다.' : '서재 기록만 지웁니다. 영상 파일은 유지됩니다.'}\n${videos.length}개 · ${videoSizeLabel({sizeBytes: total})}\n\n${names}${videos.length > 8 ? '\n…' : ''}\n\n계속하시겠습니까?`)) return;
  deletingVideos = true;
  let completed = 0; const errors = [];
  try {
    for (const video of videos) {
      const result = await sendWithPromise('internetBrowserDeleteVideo', video.url, deleteFiles);
      if (result.deleted) ++completed; else errors.push(result.error || '삭제하지 못했습니다.');
    }
  } catch { errors.push('삭제 요청에 실패했습니다.'); }
  finally {
    deletingVideos = false; await refreshLibrary();
    document.querySelector('#video-status').textContent = `${completed}개 ${deleteFiles ? '파일 삭제' : '기록 삭제'} 완료${errors.length ? ` · ${errors[0]}` : ''}`;
  }
}
document.querySelector('#select-all-videos').addEventListener('click', () => {
  const boxes = [...document.querySelectorAll('.select-video:not(:disabled)')];
  const checked = boxes.some(box => !box.checked);
  for (const box of boxes) { box.checked = checked; box.dispatchEvent(new Event('change')); }
});
document.querySelector('#hide-selected-videos').addEventListener('click', () => deleteLibraryVideos([...selectedVideos.values()], false));
document.querySelector('#delete-selected-videos').addEventListener('click', () => deleteLibraryVideos([...selectedVideos.values()], true));
async function refreshLibrary() {
if (libraryLoading || deletingVideos) return;
libraryLoading = true;
document.querySelector('#refresh-videos').disabled = true;
try {
  const library = await sendWithPromise('internetBrowserVideos');
  if (library.error) throw new Error(library.error);
  document.querySelector('#videos').replaceChildren();
  selectedVideos.clear();
  document.querySelector('#video-status').textContent = library.videos.length
    ? `${library.videos.length}개의 저장된 영상` : '저장된 영상이 없습니다.';
  if (library.privateSession) document.querySelector('#video-status').textContent += ' · 시크릿 창의 재생 기록은 저장하지 않습니다.';
  for (const video of library.videos) {
    const item = document.createElement('li');
    const link = document.createElement('button');
    const url = new URL(video.url);
    if (!['file:', 'content:'].includes(url.protocol)) continue;
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
    checkbox.className = 'select-video'; checkbox.setAttribute('aria-label', `${video.title} 선택`);
    checkbox.disabled = library.privateSession === true;
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selectedVideos.set(url.href, video); else selectedVideos.delete(url.href);
    });
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
      const title = await settingsDialog('영상 제목', link.textContent);
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
    const remove = document.createElement('button'); remove.className = 'secondary'; remove.textContent = '삭제';
    remove.disabled = library.privateSession === true;
    remove.addEventListener('click', () => deleteLibraryVideos([video], true));
    const size = document.createElement('span'); size.className = 'muted'; size.textContent = videoSizeLabel(video);
    item.append(checkbox, link, size, rename, remove);
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
const captureTab = document.querySelector('#capture-tab');
const contextVideo = new URLSearchParams(location.search);
let contextTabSelected = false;
let scanGeneration = 0;
async function refreshCaptureTabs() {
  try {
    const result = await sendWithPromise('internetBrowserCapture', 'tabs');
    const previous = captureTab.value;
    captureTab.replaceChildren();
    for (const tab of result.tabs || []) {
      const option = document.createElement('option'); option.value = tab.token;
      option.textContent = `${tab.active ? '현재 탭 · ' : ''}${tab.title || '제목 없음'} · ${tab.url}`;
      captureTab.append(option);
    }
    const rows = result.tabs || [];
    const contextTab = !previous && contextVideo.has('source') ? rows.find(tab => tab.url === contextVideo.get('source')) : null;
    captureTab.value = rows.some(tab => tab.token === previous) ? previous : (contextTab || rows.find(tab => tab.active) || rows[0])?.token || '';
    if (contextTab) contextTabSelected = true;
    if (!captureTab.value) captureStatus.textContent = '열린 웹 탭이 없습니다. 웹페이지에서 영상을 재생한 뒤 목록을 새로고침하세요.';
  } catch { captureStatus.textContent = '열린 탭 목록을 불러오지 못했습니다.'; }
}
captureTab.addEventListener('change', () => {
  ++scanGeneration;
  document.querySelector('#capture-results').replaceChildren();
  document.querySelector('#capture-reasons').replaceChildren();
  captureStatus.textContent = '선택한 탭에서 영상 찾기를 누르세요.';
});
document.querySelector('#refresh-capture-tabs').addEventListener('click', refreshCaptureTabs);
await refreshCaptureTabs();
scanButton.addEventListener('click', async () => {
  if (!captureTab.value) { captureStatus.textContent = '탭 목록에서 영상이 있는 페이지를 먼저 선택하세요.'; return; }
  scanButton.disabled = true;
  const generation = ++scanGeneration;
  captureStatus.textContent = '열린 페이지에서 영상을 찾고 있습니다…';
  document.querySelector('#capture-results').replaceChildren();
  document.querySelector('#capture-reasons').replaceChildren();
  try {
    const result = await sendWithPromise('internetBrowserCapture', 'scan', captureTab.value);
    if (generation !== scanGeneration) return;
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
      const clicked = items.findIndex(item => item.url === contextVideo.get('media'));
      if (clicked > 0) items.unshift(...items.splice(clicked, 1));
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
if (contextTabSelected) scanButton.click();
const transferHistoryKey = 'video-transfer-dismissed-v1';
function dismissedTransfers() {
  try {
    const value = JSON.parse(localStorage.getItem(transferHistoryKey) || '[]');
    return new Set(Array.isArray(value) ? value.filter(id => typeof id === 'string' && id.length <= 200).slice(0, 10000) : []);
  } catch { return new Set(); }
}
function dismissTransfers(items, guid = null) {
  const dismissed = dismissedTransfers();
  for (const item of items) {
    if ([1, 2, 3].includes(item.state) && typeof item.guid === 'string' && item.guid.length <= 200 &&
        (guid === null || guid === item.guid)) dismissed.add(item.guid);
  }
  if (dismissed.size > 10000) throw new Error('지울 수 있는 진행 기록 수를 초과했습니다.');
  // Hide progress rows only. Chromium download records and saved media remain
  // available to the library; never cancel a job or remove a file here.
  localStorage.setItem(transferHistoryKey, JSON.stringify([...dismissed]));
}
async function clearTransferHistory(guid = null) {
  try {
    const result = await sendWithPromise('internetBrowserCapture', 'transfers');
    if (result.error) throw new Error(result.error);
    dismissTransfers(result.items || [], guid);
    captureStatus.textContent = '진행 기록을 지웠습니다. 저장한 영상은 서재에 그대로 있습니다.';
  } catch (error) { captureStatus.textContent = error.message || '진행 기록을 지우지 못했습니다.'; }
  await refreshTransfers();
}
document.querySelector('#clear-video-transfers').addEventListener('click', () => clearTransferHistory());
window.addEventListener('storage', event => { if (event.key === transferHistoryKey) refreshTransfers(); });
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
    const dismissed = dismissedTransfers();
    const visibleItems = result.items.filter(item => item.state === 0 || !dismissed.has(item.guid));
    document.querySelector('#clear-video-transfers').disabled = !visibleItems.some(item => [1, 2, 3].includes(item.state));
    for (const item of visibleItems) {
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
      if ([1, 2, 3].includes(item.state)) {
        const remove = document.createElement('button'); remove.className = 'secondary';
        remove.textContent = '기록 지우기';
        remove.addEventListener('click', async () => { remove.disabled = true; await clearTransferHistory(item.guid); });
        row.append(remove);
      }
      container.append(row);
    }
    if (!visibleItems.length) container.textContent = '표시할 영상 다운로드 기록이 없습니다.';
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
const updateSecurity = document.querySelector('#update-security');
const updateLocation = document.querySelector('#update-location');
const updateProgressArea = document.querySelector('#update-progress-area');
const updateProgress = document.querySelector('#update-progress');
const updateProgressLabel = document.querySelector('#update-progress-label');
let updateDownloading = false;
let returningFromSecurity = false;
let updateCandidate;
function displayUpdateCandidate(release) {
  updateCandidate = release;
  document.querySelector('#update-title').textContent = `Internet Browser ${release.version}`;
  document.querySelector('#update-notes').textContent = release.description || '';
  document.querySelector('#update-page').href = release.releasePage;
  updateDownload.disabled = !release.canInstall;
  updateSettings.hidden = !release.android; updateSecurity.hidden = !release.android;
  updateRelease.hidden = false;
}
let recoveringUpdate = false;
async function recoverUpdate() {
  if (recoveringUpdate || updateDownloading) return;
  recoveringUpdate = true;
  try {
    const state = await sendWithPromise('internetBrowserUpdate', 'progress');
    if (!state.available || !['downloading', 'verifying', 'ready'].includes(state.phase)) return;
    displayUpdateCandidate(state);
    const active = state.phase !== 'ready';
    updateCheck.disabled = active; updateDownload.disabled = true;
    updateInstall.hidden = !state.verified; updateLocation.hidden = !state.verified;
    updateProgressArea.hidden = false;
    const total = Number(state.totalBytes) || 0, received = Number(state.receivedBytes) || 0;
    const percent = state.verified ? 100 : total ? Math.min(100, received / total * 100) : 0;
    updateProgress.value = percent;
    updateProgressLabel.textContent = state.phase === 'verifying' ? '파일 검증 중…'
      : state.verified ? '100% · 다운로드 및 파일 검증 완료'
      : `${Math.floor(percent)}% · ${(received / 1048576).toFixed(1)} MB / ${(total / 1048576).toFixed(1)} MB`;
    if (state.verified) document.querySelector('#update-return-help').hidden = !state.android;
  } catch { /* Keep the user's current controls if a state refresh fails. */ }
  finally { recoveringUpdate = false; }
}
updateAuto.checked = localStorage.getItem('update_auto_check') !== 'false';
updateAuto.addEventListener('change', () => localStorage.setItem('update_auto_check', String(updateAuto.checked)));
async function checkUpdate(automatic = false) {
  updateCheck.disabled = true;
  updateStatus.textContent = automatic ? '' : '공식 릴리스를 확인하는 중…';
  updateRelease.hidden = true;
  updateInstall.hidden = true;
  updateLocation.hidden = true;
  updateProgressArea.hidden = true;
  updateDownload.disabled = true;
  try {
    const release = await sendWithPromise('internetBrowserUpdate', 'check');
    if (release.error) throw new Error(release.error);
    localStorage.setItem('update_last_auto_check', String(Date.now()));
    if (!release.available) {updateStatus.textContent = automatic ? '' : '최신 버전을 사용 중입니다.'; return;}
    if (automatic && localStorage.getItem('update_snoozed_tag') === release.tag && Number(localStorage.getItem('update_snoozed_until')) > Date.now()) return;
    displayUpdateCandidate(release);
    await recoverUpdate();
    updateStatus.textContent = release.canInstall ? '새 버전이 있습니다. 다운로드한 파일은 설치 전에 검증합니다.' : '이 버전에는 앱에서 검증할 수 있는 설치 파일이 없습니다. 공식 릴리스를 확인해 주세요.';
  } catch (error) {
    updateStatus.textContent = automatic ? '' : error.message;
  } finally {updateCheck.disabled = false;}
}
updateCheck.addEventListener('click', () => checkUpdate());
updateDownload.addEventListener('click', async () => {
  if (updateDownloading) return;
  updateDownloading = true;
  updateDownload.disabled = true; updateCheck.disabled = true;
  updateInstall.hidden = true; updateLocation.hidden = true;
  updateProgressArea.hidden = false; updateProgress.value = 0;
  updateProgressLabel.textContent = '다운로드 준비 중…';
  updateStatus.textContent = '업데이트 다운로드 중…';
  let polling = false;
  const poll = setInterval(async () => {
    if (polling) return;
    polling = true;
    try {
      const state = await sendWithPromise('internetBrowserUpdate', 'progress');
      if (!updateDownloading) return;
      const received = Math.max(0, Number(state.receivedBytes) || 0);
      const total = Math.max(0, Number(state.totalBytes) || 0);
      const percent = total ? Math.min(100, received / total * 100) : 0;
      if (total) updateProgress.value = percent; else updateProgress.removeAttribute('value');
      const mb = bytes => `${(bytes / 1048576).toLocaleString('ko-KR', {maximumFractionDigits: 1})} MB`;
      updateProgressLabel.textContent = state.phase === 'verifying' ? '다운로드 완료 · 파일 검증 중…'
        : `${total ? `${Math.floor(percent)}% · ` : ''}${mb(received)} / ${total ? mb(total) : '용량 확인 중'}`;
    } catch { /* A failed status poll must not cancel the native download. */ }
    finally { polling = false; }
  }, 500);
  try {
    const result = await sendWithPromise('internetBrowserUpdate', 'download');
    if (result.error || !result.verified) throw new Error(result.error || '다운로드 파일을 검증하지 못했습니다.');
    updateInstall.hidden = false;
    updateLocation.hidden = false; updateProgress.value = 100;
    updateProgressLabel.textContent = '100% · 다운로드 및 파일 검증 완료';
    updateStatus.textContent = '파일 크기와 SHA-256 검증을 완료했습니다. 설치하려면 아래 버튼을 눌러 주세요.';
    if (updateCandidate.android) {
      document.querySelector('#update-return-help').hidden = false;
      returningFromSecurity = true;
      const settings = await sendWithPromise('internetBrowserUpdate', 'security');
      if (!settings.opened) updateStatus.textContent = '파일 검증 완료. 보안 설정을 직접 확인한 뒤 설치 계속하기를 눌러 주세요.';
    }
  } catch (error) {updateStatus.textContent = error.message; updateDownload.disabled = false;}
  finally {clearInterval(poll); updateDownloading = false; updateCheck.disabled = false;}
});
window.addEventListener('focus', () => {
  if (returningFromSecurity && !updateInstall.hidden) {
    returningFromSecurity = false;
    updateStatus.textContent = '설정 확인을 마쳤다면 설치 계속하기를 누르세요. 설치가 차단돼도 같은 파일로 다시 시도할 수 있습니다.';
  }
});
for (const [button, command] of [[updateSecurity, 'security'], [updateLocation, 'location']]) {
  button.addEventListener('click', async () => {
    try {
      const result = await sendWithPromise('internetBrowserUpdate', command);
      if (!result.opened) throw new Error();
      if (command === 'security') returningFromSecurity = true;
      else updateStatus.textContent = updateCandidate?.android
        ? '다운로드 화면을 열었습니다. Download/Internet Browser 폴더에 APK 복사본이 있습니다.'
        : '설치 파일이 있는 폴더를 열었습니다.';
    } catch { updateStatus.textContent = command === 'security' ? '보안 설정을 열지 못했습니다. 기기 설정에서 보안 및 개인정보 보호를 열어 주세요.' : '저장 위치를 열지 못했습니다. 설치 계속하기로 다시 시도할 수 있습니다.'; }
  });
}
updateInstall.addEventListener('click', async () => {
  if (!await settingsDialog(`Internet Browser ${updateCandidate.version} 설치 프로그램을 여시겠습니까?`)) return;
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
await recoverUpdate();
if (!updateCandidate && updateAuto.checked && (!Number.isFinite(lastCheck) || Date.now() - lastCheck >= 12 * 60 * 60 * 1000)) await checkUpdate(true);
window.addEventListener('focus', recoverUpdate);
setInterval(() => { if (!document.hidden && !updateRelease.hidden) recoverUpdate(); }, 1500);
