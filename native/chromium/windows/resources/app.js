import {sendWithPromise} from 'chrome://resources/js/cr.js';

const enabled = document.querySelector('#enabled');
const preset = document.querySelector('#preset');
const transportStatus = document.querySelector('#transport-status');
const saveStatus = document.querySelector('#save-status');
try {
  const state = await sendWithPromise('internetBrowserStatus');
  enabled.checked = state.enabled ?? false;
  preset.value = state.preset ?? 'balanced';
  transportStatus.textContent = state.status;
} catch {
  transportStatus.textContent = '연결 상태를 불러오지 못했습니다. 페이지를 다시 열어 주세요.';
}
document.querySelector('#dpi-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button');
  button.disabled = true;
  try {
    const result = await sendWithPromise('internetBrowserSave', enabled.checked, preset.value);
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
try {
  const library = await sendWithPromise('internetBrowserVideos');
  document.querySelector('#video-status').textContent = library.videos.length
    ? `${library.videos.length}개의 저장된 영상` : '저장된 영상이 없습니다.';
  for (const video of library.videos) {
    const item = document.createElement('li');
    const link = document.createElement('button');
    const url = new URL(video.url);
    if (url.protocol !== 'file:') continue;
    link.textContent = video.title;
    link.addEventListener('click', async () => {
      try {
        const result = await sendWithPromise('internetBrowserOpenVideo', url.href);
        if (!result.opened) document.querySelector('#video-status').textContent = '파일을 찾을 수 없습니다.';
      } catch {
        document.querySelector('#video-status').textContent = '영상을 열지 못했습니다.';
      }
    });
    item.append(link);
    document.querySelector('#videos').append(item);
  }
} catch {
  document.querySelector('#video-status').textContent = '영상 목록을 불러오지 못했습니다. 파일은 원래 위치에 보관되어 있습니다.';
}
