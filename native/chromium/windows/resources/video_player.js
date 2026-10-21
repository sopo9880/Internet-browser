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
// The library may retain separate original MP4 tracks. Keep one playback
// timeline and controls; never silently play a video-only download as a movie.
const companion = typeof options.audioUrl === 'string' ? document.createElement('audio') : null;
if (companion) {
  companion.id = 'internet-browser-companion-audio'; companion.hidden = true;
  companion.preload = 'auto'; companion.src = options.audioUrl; root.append(companion);
  video.pause();
}
const syncCompanion = () => {
  if (!companion) return;
  companion.volume = video.volume; companion.muted = video.muted;
  companion.playbackRate = video.playbackRate;
  if (companion.readyState >= 1 && Number.isFinite(video.currentTime) && Math.abs(companion.currentTime - video.currentTime) > 0.15)
    companion.currentTime = video.currentTime;
};
const startPlayback = () => {
  syncCompanion();
  const tasks = [video.play()]; if (companion) tasks.push(companion.play());
  return Promise.all(tasks).catch(() => {
    video.pause(); companion?.pause(); status.textContent = '영상과 음성을 재생하지 못했습니다. 재생 버튼을 다시 눌러 주세요.';
  });
};
if (companion) {
  for (const name of ['seeking', 'seeked', 'timeupdate', 'ratechange', 'volumechange']) video.addEventListener(name, syncCompanion);
  video.addEventListener('pause', () => companion.pause());
  video.addEventListener('playing', () => {if (video.paused) return; syncCompanion(); companion.play().catch(() => {video.pause(); status.textContent = '음성을 재생하지 못했습니다. 재생 버튼을 다시 눌러 주세요.';});});
  video.addEventListener('waiting', () => companion.pause());
  companion.addEventListener('loadedmetadata', syncCompanion);
  companion.addEventListener('error', () => {video.pause(); status.textContent = '저장된 음성 파일을 재생하지 못했습니다.';});
  window.addEventListener('pagehide', () => companion.pause(), {once: true});
}
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
const toggle = () => video.paused ? startPlayback() : video.pause();
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
const captionChoice = document.createElement('select');
captionChoice.setAttribute('aria-label', '자막 선택');
const selectCaption = index => {
  [...video.textTracks].forEach((track, current) => {track.mode = current === index ? 'showing' : 'disabled';});
  captionChoice.value = String(index);
};
const refreshCaptions = () => {
  captionChoice.replaceChildren();
  for (const [index, label] of [[-1, '자막 끄기'], ...[...video.textTracks].map((track, index) => [index, track.label || track.language || `자막 ${index + 1}`])]) {
    const option = document.createElement('option'); option.value = index; option.textContent = label; captionChoice.append(option);
  }
  captionChoice.value = String([...video.textTracks].findIndex(track => track.mode === 'showing'));
  captionChoice.disabled = video.textTracks.length === 0;
};
const captions = () => {
  const current = [...video.textTracks].findIndex(track => track.mode === 'showing');
  selectCaption(current < 0 && video.textTracks.length ? 0 : -1);
};
button('자막', captions);
captionChoice.addEventListener('change', () => selectCaption(Number(captionChoice.value)));
toolbar.append(captionChoice);
video.textTracks.addEventListener('addtrack', refreshCaptions);
video.textTracks.addEventListener('removetrack', refreshCaptions);
video.textTracks.addEventListener('change', refreshCaptions);
refreshCaptions();
const subtitleVtt = subtitle => {
  const text = subtitle.text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
  if (subtitle.format === 'vtt') return /^WEBVTT(?:[ \t\n]|$)/.test(text) ? text : '';
  const literal = text => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const timestamp = value => {
    const match = /^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})$/.exec(value.trim());
    if (!match || Number(match[2]) > 59 || Number(match[3]) > 59) return '';
    return `${match[1].padStart(2, '0')}:${match[2]}:${match[3]}.${match[4].padEnd(3, '0')}`;
  };
  const cues = [];
  if (subtitle.format === 'srt') {
    for (const block of text.split(/\n[ \t]*\n/)) {
      const lines = block.split('\n');
      if (/^\d+$/.test(lines[0]?.trim())) lines.shift();
      const times = lines.shift()?.split('-->');
      if (!times || times.length !== 2) continue;
      const start = timestamp(times[0]), end = timestamp(times[1]);
      if (start && end && lines.length) cues.push(`${start} --> ${end}\n${literal(lines.join('\n'))}`);
    }
  } else if (subtitle.format === 'ass') {
    // Preserve dialogue timing/text. ASS positioning, fonts and effects are not applied.
    let events = false, fields = [];
    for (const line of text.split('\n')) {
      if (/^\[.*\]$/.test(line.trim())) {events = line.trim().toLowerCase() === '[events]'; continue;}
      if (!events) continue;
      if (/^Format:/i.test(line)) {fields = line.slice(line.indexOf(':') + 1).split(',').map(x => x.trim().toLowerCase()); continue;}
      if (!/^Dialogue:/i.test(line) || fields.at(-1) !== 'text') continue;
      const parts = line.slice(line.indexOf(':') + 1).split(',');
      if (parts.length < fields.length) continue;
      const start = timestamp(parts[fields.indexOf('start')] || ''), end = timestamp(parts[fields.indexOf('end')] || '');
      const dialogue = parts.slice(fields.length - 1).join(',').replace(/\{[^}]*\}/g, '').replace(/\\[Nn]/g, '\n').replace(/\\h/g, ' ');
      if (start && end && dialogue) cues.push(`${start} --> ${end}\n${literal(dialogue)}`);
    }
  }
  return cues.length ? 'WEBVTT\n\n' + cues.join('\n\n') + '\n' : '';
};
if (typeof options.subtitle?.text === 'string' && options.subtitle.text.length <= 2 * 1024 * 1024) {
  const vtt = subtitleVtt(options.subtitle);
  if (vtt) {
    const track = document.createElement('track'); track.kind = 'subtitles';
    track.label = options.subtitle.label || '외부 자막'; track.default = true;
    const blob = URL.createObjectURL(new Blob([vtt], {type: 'text/vtt;charset=utf-8'}));
    track.src = blob;
    track.addEventListener('load', () => {selectCaption([...video.textTracks].indexOf(track.track)); refreshCaptions();});
    track.addEventListener('error', () => {status.textContent = '외부 자막을 읽지 못했습니다.'; URL.revokeObjectURL(blob);});
    video.append(track); track.track.mode = 'showing';
    window.addEventListener('pagehide', () => URL.revokeObjectURL(blob), {once: true});
  } else status.textContent = '외부 자막의 형식을 읽지 못했습니다.';
}
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
  for (const [action, handler] of Object.entries({play: startPlayback, pause: () => video.pause(),
    seekbackward: details => seekBy(-(details.seekOffset || 10)), seekforward: details => seekBy(details.seekOffset || 10),
    seekto: details => {if (Number.isFinite(details.seekTime)) video.currentTime = details.seekTime;},
    nexttrack: () => {if (options.hasNext) move('next');}, previoustrack: () => {if (options.hasPrevious) move('previous');}})) {
    try {navigator.mediaSession.setActionHandler(action, handler);} catch {}
  }
}
refresh();
