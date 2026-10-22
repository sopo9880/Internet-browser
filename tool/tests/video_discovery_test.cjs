const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../../native/chromium/windows/resources/video_discovery.js'), 'utf8');
function scan({videos = [], scripts = [], metas = [], resources = [], links = [], baseURI = 'https://example.test/watch'} = {}) {
  const document = {
    title: '한글 영상', URL: baseURI, baseURI, scripts,
    querySelector: () => null,
    querySelectorAll: selector => selector === 'video' ? videos : selector.startsWith('meta[') ? metas : selector.startsWith('a[') ? links : []
  };
  return JSON.parse(JSON.stringify(vm.runInNewContext(script, {document, performance: {getEntriesByType: () => resources}, URL})));
}
const video = (src, options = {}) => ({currentSrc: src, src, videoHeight: 720,
  getAttribute: name => name === 'type' ? 'video/mp4' : null,
  querySelectorAll: () => [], ...options});
test('DOM media, relative URLs, metadata and request history are unified and deduplicated', () => {
  const result = scan({videos: [video('/clip.mp4')], metas: [{content: 'https://cdn.test/reel.mp4'}],
    resources: [{name: 'https://cdn.test/master.m3u8'}, {name: 'https://example.test/clip.mp4'}]});
  assert.equal(result.items.length, 3);
  assert.equal(result.items[0].quality, '720p');
  assert.equal(result.items[0].title, '한글 영상');
  assert.equal(result.items[2].kind, 'hls');
});
test('unsafe schemes and embedded credentials cannot become candidates', () => {
  const result = scan({videos: [video('file:///secret.mp4'), video('javascript:alert(1)'),
    video('https://name:secret@example.test/a.mp4'), video('data:video/mp4,abc')]});
  assert.equal(result.items.length, 0);
});
test('DRM and unresolved blob media explain inability to save', () => {
  assert.equal(scan({videos: [video('https://cdn.test/drm.mp4', {mediaKeys: {}})]}).items.length, 0);
  const result = scan({videos: [video('blob:https://example.test/id')]});
  assert.equal(result.items.length, 0);
  assert.ok(result.reasons.some(reason => reason.includes('스트림')));
});
test('YouTube embedded JSON handles quoted braces without evaluating page code', () => {
  const payload = {videoDetails: {title: 'a } " title'}, streamingData: {formats: [
    {url: 'https://cdn.test/play?mime=video', mimeType: 'video/mp4; codecs="avc1, mp4a"', qualityLabel: '360p'},
    {signatureCipher: 's=secret', mimeType: 'video/mp4'}
  ]}};
  const result = scan({scripts: [{type: '', textContent: 'var ytInitialPlayerResponse = ' + JSON.stringify(payload) + '; throw new Error("must not execute");'}]});
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].quality, '360p');
  assert.ok(result.reasons.some(reason => reason.includes('서명')));
});
test('Instagram JSON video_url and JSON-LD contentUrl are found; malformed data is harmless', () => {
  const result = scan({scripts: [
    {type: 'application/json', textContent: '{invalid'},
    {type: 'application/json', textContent: JSON.stringify({data: {video_url: 'https://cdn.test/reel?id=7'}})},
    {type: 'application/ld+json', textContent: JSON.stringify({contentUrl: 'https://cdn.test/clip.mp4'})}
  ]});
  assert.equal(result.items.length, 2);
});
test('candidate count and script bytes are bounded on hostile pages', () => {
  const result = scan({resources: Array.from({length: 2000}, (_, n) => ({name: `https://cdn.test/${n}.mp4`}))});
  assert.equal(result.items.length, 60);
  assert.equal(scan({scripts: [{type: 'application/json', textContent: ' '.repeat(2097153)}]}).items.length, 0);
});
test('YouTube SPA navigation does not reuse the previous video response', () => {
  const payload = {videoDetails: {videoId: 'oldvideo123'}, streamingData: {formats: [
    {url: 'https://cdn.test/old.mp4', mimeType: 'video/mp4', qualityLabel: '360p'}
  ]}};
  const result = scan({baseURI: 'https://www.youtube.com/watch?v=newvideo123',
    scripts: [{type: '', textContent: 'var ytInitialPlayerResponse = '+JSON.stringify(payload)+';'}]});
  assert.equal(result.items.length, 0);
  assert.ok(result.reasons.some(reason=>reason.includes('바뀌었습니다')));
});
test('a loaded extensionless video remains discoverable without inventing its container', () => {
  const result = scan({videos: [video('https://cdn.test/play?id=5', {getAttribute: ()=>null})]});
  assert.equal(result.items[0].mime, 'video/unknown');
  assert.equal(result.documentUrl, 'https://example.test/watch');
});
test('unciphered YouTube adaptive MP4 formats retain the selected video and highest-bitrate audio', () => {
  const payload = {streamingData:{adaptiveFormats:[
    {url:'https://cdn.test/video.mp4',mimeType:'video/mp4; codecs="avc1"',qualityLabel:'1080p'},
    {url:'https://cdn.test/a-low.m4a',mimeType:'audio/mp4',bitrate:64000},
    {url:'https://cdn.test/a-high.m4a',mimeType:'audio/mp4',bitrate:128000},
    {url:'file:///private.m4a',mimeType:'audio/mp4',bitrate:999999}
  ]}};
  const result=scan({scripts:[{type:'',textContent:'var ytInitialPlayerResponse = '+JSON.stringify(payload)+';'}]});
  assert.equal(result.items.length,1);assert.equal(result.items[0].kind,'pair');
  assert.equal(result.items[0].quality,'1080p');assert.equal(result.items[0].audioUrl,'https://cdn.test/a-high.m4a');
});

test('real YouTube pages use native public HLS discovery instead of unusable raw WEB URLs', () => {
  const payload = {responseContext: {visitorData: 'anonymous-visitor'}, videoDetails:{videoId:'KMH4gUTuYJs'}, streamingData:{
    formats:[{url:'https://rr1.googlevideo.com/videoplayback?n=unprocessed',mimeType:'video/mp4',qualityLabel:'360p'}],
    adaptiveFormats:[{itag:299,mimeType:'video/mp4',qualityLabel:'1080p60'}],serverAbrStreamingUrl:'https://rr1.googlevideo.com/sabr'}};
  const result = scan({baseURI:'https://www.youtube.com/watch?v=KMH4gUTuYJs',
    scripts:[{type:'',textContent:'var ytInitialPlayerResponse = '+JSON.stringify(payload)+';'}]});
  assert.equal(result.items.length,1);assert.equal(result.items[0].kind,'youtube');
  assert.equal(result.items[0].url,'https://www.youtube.com/watch?v=KMH4gUTuYJs');
  assert.equal(result.items[0].visitorData,'anonymous-visitor');
  assert.equal(result.items[0].quality,'제공 화질 확인');
});

test('visitor config is read as bounded JSON without executing script', () => {
  const result=scan({baseURI:'https://www.youtube.com/watch?v=KMH4gUTuYJs',scripts:[{type:'',
    textContent:'ytcfg.set({"VISITOR_DATA":"anonymous"}); throw new Error("never execute");'}]});
  assert.equal(result.items[0].kind,'youtube');assert.equal(result.items[0].visitorData,'anonymous');
  assert.equal(scan({baseURI:'https://www.youtube.com/watch?v=KMH4gUTuYJs',scripts:[{type:'',
    textContent:JSON.stringify({VISITOR_DATA:'x'.repeat(4097)})}]}).items.length,0);
});

test('native YouTube discovery cannot be requested from lookalike hosts or DRM media', () => {
  const scripts=[{type:'',textContent:'ytcfg.set({"VISITOR_DATA":"anonymous"});'}];
  assert.equal(scan({baseURI:'https://www.youtube.com.attacker.test/watch?v=KMH4gUTuYJs',scripts}).items.length,0);
  assert.equal(scan({baseURI:'https://www.youtube.com/watch?v=KMH4gUTuYJs',scripts,
    videos:[video('blob:https://www.youtube.com/id',{mediaKeys:{}})]}).items.length,0);
});

test('native HLS size hints include audio and work without direct WEB URLs', () => {
  const payload={responseContext:{visitorData:'anonymous'},videoDetails:{videoId:'KMH4gUTuYJs'},streamingData:{adaptiveFormats:[
    {mimeType:'video/mp4; codecs="avc1.64002a"',qualityLabel:'1080p60',contentLength:'300000000'},
    {mimeType:'video/mp4; codecs="av01"',qualityLabel:'1080p60',contentLength:'999999999'},
    {mimeType:'video/mp4; codecs="avc1"',qualityLabel:'720p',contentLength:'-1'},
    {mimeType:'audio/mp4; codecs="mp4a.40.2"',contentLength:'12000000',bitrate:128000}
  ]}};
  const result=scan({baseURI:'https://www.youtube.com/watch?v=KMH4gUTuYJs',scripts:[
    {type:'',textContent:'var ytInitialPlayerResponse = '+JSON.stringify(payload)+';'}]});
  assert.equal(result.items[0].sizeHints['1080p60'],312000000);
  assert.equal(result.items[0].sizeHints['720p'],undefined);
});

test('direct pair sizes require both known file lengths and reject malformed lengths', () => {
  function result(audioLength) {
    return scan({scripts:[{type:'application/json',textContent:JSON.stringify({streamingData:{adaptiveFormats:[
      {url:'https://cdn.test/v.mp4',mimeType:'video/mp4',qualityLabel:'1080p',contentLength:'1000'},
      {url:'https://cdn.test/a.m4a',mimeType:'audio/mp4',contentLength:audioLength}
    ]}})}]}).items[0];
  }
  assert.equal(result('200').sizeBytes,1200);assert.equal(result('200').sizeEstimated,false);
  for(const invalid of [undefined,-1,true,'NaN','9007199254740992']) assert.equal(result(invalid).sizeBytes,undefined);
});
