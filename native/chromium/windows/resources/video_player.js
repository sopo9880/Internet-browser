// Runs only in the browser's internal isolated world on an approved library file.
const video = document.querySelector('video');
if (!video || document.querySelector('#internet-browser-player')) return;
const send = (action, extra = {}) => console.info('INTERNET_BROWSER_LOCAL_PLAYER:' + JSON.stringify({action, ...extra}));
const root = document.createElement('main');
root.id = 'internet-browser-player';
const style = document.createElement('style');
style.textContent = `
#internet-browser-player{position:fixed;inset:0;display:flex;flex-direction:column;background:#080b10;color:#fff;font:14px system-ui,sans-serif;z-index:2147483647}
#internet-browser-player video{display:block;flex:1;min-height:0;width:100%;height:100%;object-fit:contain;background:#000}
#internet-browser-player .ib-controls{flex-shrink:0;padding:12px 18px;background:#14212d;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
#internet-browser-player button,#internet-browser-player select{font:inherit;padding:8px 12px;border:1px solid #627483;border-radius:7px;background:#243d50;color:#fff;cursor:pointer}
#internet-browser-player button:focus-visible,#internet-browser-player input:focus-visible,#internet-browser-player select:focus-visible{outline:3px solid #8fd3ff;outline-offset:2px}
#internet-browser-player button:disabled{opacity:.4;cursor:default}
#internet-browser-player .ib-title{margin:0 auto 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70vw;font-size:15px}
#internet-browser-player .ib-seek{flex:1;min-width:150px}#internet-browser-player .ib-volume{width:90px}
#internet-browser-player .ib-status{margin:0;color:#ffce8b;width:100%}#internet-browser-player .ib-status:empty{display:none}
#internet-browser-player.ib-hidden .ib-controls{display:none}
#internet-browser-player.ib-locked .ib-controls>:not(.ib-unlock):not(.ib-title){display:none}
#internet-browser-player .ib-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
@media(max-width:600px){#internet-browser-player .ib-controls{padding:8px;gap:8px}#internet-browser-player button{padding:8px}.ib-title{width:100%}}
`;
document.head.append(style);
video.parentNode.insertBefore(root, video);
root.append(video);
// MediaDocument assigns inline absolute positioning; explicitly replace it.
video.style.cssText = 'position:static;display:block;flex:1 1 0%;min-height:0;width:100%;height:0;margin:0;background:#000;object-fit:contain';
const toolbar = document.createElement('div');
toolbar.className = 'ib-controls';
toolbar.setAttribute('role', 'group');
toolbar.setAttribute('aria-label', '동영상 재생 조작');
root.append(toolbar);
const title = document.createElement('h1');
title.className = 'ib-title';
title.textContent = options.title || options.name || '저장된 영상';
document.title = title.textContent;
toolbar.append(title);
const status = document.createElement('p');
status.className = 'ib-status';
status.setAttribute('role', 'status');
const button = (label, action) => {
  const element = document.createElement('button');
  element.type = 'button'; element.textContent = label;
  element.addEventListener('click', action); toolbar.append(element); return element;
};
const range = (label, min, max, step, value, className) => {
  const element = document.createElement('input');
  element.type = 'range'; element.min = min; element.max = max;
  element.step = step; element.value = value; element.className = className;
  element.setAttribute('aria-label', label); toolbar.append(element); return element;
};
let rate = Number.isFinite(options.rate) ? options.rate : 1;
let locked = false;
let fastTimer;
let temporaryFast = false;
let lastSaved = -1;
let resumeApplied = false;
const report = (force = false) => {
  if (!Number.isFinite(video.currentTime) || !Number.isFinite(video.duration)) return;
  if (!force && Math.floor(video.currentTime / 10) === lastSaved) return;
  lastSaved = Math.floor(video.currentTime / 10);
  send('position', {positionMs: Math.round(video.currentTime * 1000), durationMs: Math.round(video.duration * 1000)});
};
const state = () => ({rate, volume: video.volume, fit: video.style.objectFit, loop: video.loop});
const move = action => {report(true); send(action, state());};
const previous = button('이전', () => move('previous'));
previous.disabled = !options.hasPrevious;
const toggle = () => video.paused ? video.play().catch(() => {status.textContent = '재생 버튼을 다시 눌러 주세요.';}) : video.pause();
const play = button('재생', toggle);
const next = button('다음', () => move('next'));
next.disabled = !options.hasNext;
const lock = button('잠금', () => {
  locked = !locked; root.classList.toggle('ib-locked', locked);
  root.classList.remove('ib-hidden'); lock.textContent = locked ? '잠금 해제' : '잠금';
  if (locked) endFast();
});
lock.className = 'ib-unlock';
const seek = range('재생 위치', 0, 100, 0.1, 0, 'ib-seek');
seek.addEventListener('input', () => {
  if (Number.isFinite(video.duration)) video.currentTime = video.duration * Number(seek.value) / 100;
});
seek.addEventListener('change', () => report(true));
const clock = document.createElement('span'); toolbar.append(clock);
const formatTime = time => {
  if (!Number.isFinite(time)) return '00:00';
  const total = Math.max(0, Math.floor(time));
  const seconds = String(total % 60).padStart(2, '0');
  const minutes = String(Math.floor(total / 60) % 60).padStart(2, '0');
  return total >= 3600 ? `${Math.floor(total / 3600)}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
};
const volume = range('음량', 0, 1, 0.05, options.volume ?? 1, 'ib-volume');
video.volume = Number(volume.value);
volume.addEventListener('input', () => {video.volume = Number(volume.value); video.muted = false;});
const speed = document.createElement('select');
speed.setAttribute('aria-label', '재생 배속');
for (const value of [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]) {
  const option = document.createElement('option'); option.value = value; option.textContent = `${value}×`; speed.append(option);
}
speed.value = rate; video.playbackRate = rate;
const setRate = value => {rate = Math.max(0.25, Math.min(2, value)); speed.value = rate; video.playbackRate = temporaryFast ? 2 : rate;};
speed.addEventListener('change', () => setRate(Number(speed.value))); toolbar.append(speed);
video.loop = options.loop === true;
const loop = button(video.loop ? '반복 켜짐' : '반복 꺼짐', () => {
  video.loop = !video.loop; loop.textContent = video.loop ? '반복 켜짐' : '반복 꺼짐';
});
video.style.objectFit = options.fit === 'cover' ? 'cover' : 'contain';
button('화면 맞춤', () => {video.style.objectFit = video.style.objectFit === 'cover' ? 'contain' : 'cover';});
const captions = () => {
  for (const track of video.textTracks) track.mode = track.mode === 'showing' ? 'disabled' : 'showing';
};
const captionButton = button('자막', captions);
captionButton.disabled = video.textTracks.length === 0;
video.textTracks.addEventListener('addtrack', () => {captionButton.disabled = false;});
const pip = button('작은 화면', async () => {
  try {if (document.pictureInPictureElement) await document.exitPictureInPicture(); else await video.requestPictureInPicture();}
  catch {status.textContent = '현재 기기 또는 영상에서는 작은 화면 재생을 사용할 수 없습니다.';}
});
pip.disabled = !document.pictureInPictureEnabled || !video.requestPictureInPicture;
button('전체 화면', async () => {
  try {if (document.fullscreenElement) await document.exitFullscreen(); else await root.requestFullscreen();}
  catch {status.textContent = '전체 화면을 열지 못했습니다.';}
});
const help = document.createElement('span'); help.className = 'ib-sr';
help.textContent = 'Space/K 재생·일시정지, J/L 10초 이동, 방향키 5초 이동·음량, M 음소거, F 조작 숨김, C 자막, 쉼표/마침표 배속, 숫자 위치 이동';
toolbar.append(help, status);
const seekBy = seconds => {
  if (Number.isFinite(video.duration)) video.currentTime = Math.max(0, Math.min(video.duration, video.currentTime + seconds));
};
const endFast = () => {clearTimeout(fastTimer); temporaryFast = false; video.playbackRate = rate;};
video.addEventListener('pointerdown', event => {
  if (locked || event.button !== 0) return;
  fastTimer = setTimeout(() => {temporaryFast = true; video.playbackRate = 2;}, 450);
});
for (const name of ['pointerup', 'pointercancel', 'blur']) window.addEventListener(name, endFast);
video.addEventListener('dblclick', event => {
  if (locked) return;
  const bounds = video.getBoundingClientRect();
  seekBy(event.clientX - bounds.left < bounds.width / 2 ? -10 : 10);
});
window.addEventListener('keydown', event => {
  if (locked || event.ctrlKey || event.altKey || event.metaKey ||
      ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(event.target.tagName)) return;
  const key = event.key.toLowerCase();
  if (key === ' ' || key === 'k') toggle();
  else if (key === 'j') seekBy(-10);
  else if (key === 'l') seekBy(10);
  else if (key === 'arrowleft') seekBy(-5);
  else if (key === 'arrowright') seekBy(5);
  else if (key === 'arrowup' || key === 'arrowdown') {
    video.volume = Math.max(0, Math.min(1, video.volume + (key === 'arrowup' ? 0.05 : -0.05)));
    volume.value = video.volume;
  } else if (key === 'm') video.muted = !video.muted;
  else if (key === 'f') root.classList.toggle('ib-hidden');
  else if (key === 'c') captions();
  else if (key === ',') setRate(rate - 0.25);
  else if (key === '.') setRate(rate + 0.25);
  else if (/^[0-9]$/.test(key) && Number.isFinite(video.duration)) video.currentTime = video.duration * Number(key) / 10;
  else return;
  event.preventDefault();
});
const restore = () => {
  if (resumeApplied || !Number.isFinite(video.duration)) return;
  resumeApplied = true;
  const saved = Number(options.lastPositionMs) / 1000;
  if (Number.isFinite(saved) && saved > 0 && saved < video.duration - 1) video.currentTime = saved;
};
video.addEventListener('loadedmetadata', restore); restore();
const refresh = () => {
  play.textContent = video.paused ? '재생' : '일시정지';
  clock.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`;
  if (video.duration > 0) seek.value = video.currentTime * 100 / video.duration;
};
video.controls = false;
for (const name of ['play', 'pause', 'timeupdate', 'loadedmetadata']) video.addEventListener(name, refresh);
video.addEventListener('timeupdate', () => report());
video.addEventListener('pause', () => report(true));
video.addEventListener('ended', () => {report(true); if (!video.loop && options.hasNext) move('next');});
video.addEventListener('error', () => {status.textContent = '영상을 재생하지 못했습니다. 파일 손상 또는 지원되지 않는 형식인지 확인해 주세요.';});
window.addEventListener('pagehide', () => report(true));
if (navigator.mediaSession) {
  navigator.mediaSession.metadata = new MediaMetadata({title: title.textContent, artist: 'Internet Browser'});
  for (const [action, handler] of Object.entries({play: () => video.play(), pause: () => video.pause(),
    seekbackward: details => seekBy(-(details.seekOffset || 10)), seekforward: details => seekBy(details.seekOffset || 10),
    seekto: details => {if (Number.isFinite(details.seekTime)) video.currentTime = details.seekTime;},
    nexttrack: () => {if (options.hasNext) move('next');}, previoustrack: () => {if (options.hasPrevious) move('previous');}})) {
    try {navigator.mediaSession.setActionHandler(action, handler);} catch {}
  }
}
refresh();
