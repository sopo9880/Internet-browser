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
