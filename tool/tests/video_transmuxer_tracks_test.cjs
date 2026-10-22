const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const bundled = spawnSync(process.env.NATIVE_TEST_PYTHON || (process.platform === 'win32' ? 'python' : 'python3'),
  ['-X', 'utf8', '-m', 'tool.chromium.video_transmuxer'], {cwd:root, encoding:'utf8'});
assert.equal(bundled.status, 0, bundled.stderr || String(bundled.error));
const factory = bundled.stdout;
const script = fs.readFileSync(path.join(root, 'native/chromium/windows/resources/video_transmuxer.js'), 'utf8');
// Self-generated 0.12-second stereo silence: ffmpeg anullsrc, 44100 Hz, AAC/ADTS.
const silence = Buffer.from('//FQgAOf/NwATGF2YzYzLjEuMTAwAEIgCMEYOP/xUIABv/whEARgjBz/8VCAAb/8IRAEYIwc//FQgAG//CEQBGCMHP/xUIABv/whEARgjBz/8VCAAb/8IRAEYIwc//FQgAG//CEQBGCMHA==', 'base64');
function run(context, options = {}) {
  const request={id:'audio-test', audio:true, first:true, last:true, data:silence.toString('base64'), ...options};
  return vm.runInContext(`(() => {const request=${JSON.stringify(request)}; const create=${request.first?factory:'null'};\n${script}\n})()`, context);
}
function boxes(bytes, start=0, end=bytes.length, result=[]) {
  while(start<end) {
    const size=bytes.readUInt32BE(start), type=bytes.subarray(start+4,start+8).toString();
    assert.ok(size>=8 && start+size<=end);
    result.push({type, payload:bytes.subarray(start+8,start+size)});
    if(['moov','trak','mvex','moof','traf'].includes(type)) boxes(bytes,start+8,start+size,result);
    start+=size;
  }
  return result;
}
test('AAC-only conversion writes valid nonzero track IDs and preserves compressed samples', () => {
  const context=vm.createContext({atob,btoa});
  const result=run(context); assert.equal(result.ok,true);
  const output=Buffer.from(result.data,'base64');
  const parsed=boxes(output);
  assert.equal(output.subarray(4,8).toString(),'ftyp');
  assert.equal(parsed.find(b=>b.type==='tkhd').payload.readUInt32BE(12),1);
  assert.equal(parsed.find(b=>b.type==='trex').payload.readUInt32BE(4),1);
  assert.equal(parsed.find(b=>b.type==='tfhd').payload.readUInt32BE(4),1);
  const Original=vm.runInNewContext(factory), muxer=new Original({remux:true,keepOriginalTimestamps:false});
  let original; muxer.on('data', segment=>{original=Buffer.from(segment.data);});
  muxer.push(new Uint8Array(silence)); muxer.flush();
  assert.deepEqual(parsed.find(b=>b.type==='mdat').payload, boxes(original).find(b=>b.type==='mdat').payload);
  assert.equal(vm.runInContext("globalThis[Symbol.for('internetBrowser.videoTransmuxers')].size",context),0);
});
test('track changes and invalid input fail without leaking a transmux session', () => {
  const context=vm.createContext({atob,btoa});
  assert.equal(run(context,{last:false}).ok,true);
  assert.equal(run(context,{first:false,audio:false}).ok,false);
  assert.equal(vm.runInContext("globalThis[Symbol.for('internetBrowser.videoTransmuxers')].size",context),0);
  assert.equal(run(context,{data:Buffer.from('not media').toString('base64')}).ok,false);
  assert.equal(run(context,{audio:false}).ok,false); // An audio file must not be registered as a video.
});
