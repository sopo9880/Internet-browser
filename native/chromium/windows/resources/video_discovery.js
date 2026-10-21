(() => {
  'use strict';
  const items = new Map();
  const reasons = new Set();
  const title = (document.querySelector('meta[property="og:title"]')?.content || document.title || '영상').slice(0, 200);
  const protectedMedia = [...document.querySelectorAll('video')].some(v => v.mediaKeys);
  function add(address, type = '', quality = '', source = 'page') {
    if (typeof address !== 'string' || address.length > 16384 || items.size >= 60) return;
    let url;
    try { url = new URL(address, document.baseURI); } catch { return; }
    if (url.protocol === 'blob:') { reasons.add('이 영상은 브라우저 안에서 조합되는 스트림입니다. 원본 스트림을 확인해야 합니다.'); return; }
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return;
    const mime = String(type).slice(0, 256).split(';')[0].trim().toLowerCase();
    const path = url.pathname.toLowerCase();
    let kind = /\.m3u8$/.test(path) || mime.includes('mpegurl') ? 'hls'
      : /\.mpd$/.test(path) || mime === 'application/dash+xml' ? 'dash' : 'file';
    if (kind === 'file' && !mime.startsWith('video/') && !/\.(mp4|webm|mov|m4v|mkv|avi|3gp|m2ts|ts|flv)$/.test(path)) return;
    if (protectedMedia) { reasons.add('보호된 재생이 감지되어 이 페이지의 영상을 저장할 수 없습니다.'); return; }
    const key = url.href;
    const previous = items.get(key);
    if (previous && (!quality || previous.quality)) return;
    items.set(key, {url: key, title, kind, mime, quality: String(quality || '').slice(0, 80), source});
  }
  for (const video of document.querySelectorAll('video')) {
    add(video.currentSrc || video.src, video.getAttribute('type') || (video.videoHeight > 0 ? 'video/unknown' : ''), video.videoHeight ? `${video.videoHeight}p` : '');
    for (const source of video.querySelectorAll('source')) add(source.src, source.type, source.getAttribute('label') || '');
  }
  for (const meta of document.querySelectorAll('meta[property="og:video"],meta[property="og:video:url"],meta[property="og:video:secure_url"]'))
    add(meta.content, document.querySelector('meta[property="og:video:type"]')?.content || '');
  for (const link of document.querySelectorAll('a[download],a[type^="video/"]')) add(link.href, link.type);
  for (const resource of performance.getEntriesByType('resource').slice(-1000)) add(resource.name);

  // Read embedded data as JSON only. Never execute a page script or decipher a
  // protected/signature-cipher stream. Walk bounded JSON for Instagram/JSON-LD.
  function walk(value, depth = 0, budget = {left: 8000}) {
    if (!value || typeof value !== 'object' || depth > 12 || --budget.left < 0) return;
    if (value.streamingData) {
      const page = new URL(document.baseURI);
      const id = page.pathname === '/watch' ? page.searchParams.get('v') : /^\/(shorts|embed|live)\//.test(page.pathname) ? page.pathname.split('/')[2] : null;
      if (/(^|\.)youtube\.com$/.test(page.hostname) && id && value.videoDetails?.videoId && value.videoDetails.videoId !== id) {
        reasons.add('페이지의 영상이 바뀌었습니다. 원본 탭을 새로고침한 뒤 다시 검사하세요.'); return;
      }
      const streams = value.streamingData;
      for (const format of streams.formats || []) {
        if (format.url) add(format.url, format.mimeType, format.qualityLabel || format.quality, 'youtube');
        else if (format.signatureCipher || format.cipher) reasons.add('이 YouTube 영상은 서명 처리가 필요한 스트림만 제공합니다. 현재 저장할 수 없습니다.');
      }
      if (streams.hlsManifestUrl) add(streams.hlsManifestUrl, 'application/vnd.apple.mpegurl', '', 'youtube');
      if (streams.dashManifestUrl) add(streams.dashManifestUrl, 'application/dash+xml', '', 'youtube');
      if (!(streams.formats || []).some(f => f.url) && streams.adaptiveFormats?.length)
        reasons.add('이 YouTube 영상은 영상·음성 트랙이 분리되어 있습니다. 합치기 지원이 필요합니다.');
    }
    for (const [key, child] of Object.entries(value)) {
      if (typeof child === 'string' && ['video_url', 'contentUrl', 'content_url'].includes(key)) add(child, 'video/mp4');
      else if (child && typeof child === 'object') walk(child, depth + 1, budget);
    }
  }
  function embeddedPlayer(text) {
    const marker = /(?:var\s+)?ytInitialPlayerResponse\s*=\s*/g;
    const match = marker.exec(text);
    if (!match || text[marker.lastIndex] !== '{') return;
    let quoted = false, escaped = false, depth = 0;
    const start = marker.lastIndex;
    for (let i = start; i < text.length; ++i) {
      const c = text[i];
      if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; }
      else if (c === '"') quoted = true;
      else if (c === '{') ++depth;
      else if (c === '}' && --depth === 0) { try { walk(JSON.parse(text.slice(start, i + 1))); } catch {} return; }
    }
  }
  let bytes = 0;
  for (const script of document.scripts) {
    const text = script.textContent;
    if (text.length > 2 * 1024 * 1024 || (bytes += text.length) > 8 * 1024 * 1024) continue;
    if (script.type === 'application/ld+json' || script.type === 'application/json') { try { walk(JSON.parse(text)); } catch {} }
    else if (text.includes('ytInitialPlayerResponse')) embeddedPlayer(text);
  }
  return {documentUrl: document.URL, items: [...items.values()], reasons: [...reasons]};
})()
