// request/create are supplied by the browser in its internal isolated world.
// The static source closure has no network/module-loader dependencies.
const registryKey = Symbol.for('internetBrowser.videoTransmuxers');
const registry = globalThis[registryKey] ||= new Map();
let state = registry.get(request.id);
// mux.js's raw AAC path omits the track ID, producing ISO BMFF track 0.
// Normalize only that metadata to the valid ID 1; encoded samples are untouched.
function audioTrackIds(input) {
  const bytes = new Uint8Array(input);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let boxes = 0;
  function walk(start, end, depth = 0) {
    if (depth > 6) throw new Error('Invalid MP4 nesting');
    while (start < end) {
      if (++boxes > 1024 || start + 8 > end) throw new Error('Invalid MP4 box');
      const size = view.getUint32(start);
      if (size < 8 || size > end - start) throw new Error('Invalid MP4 size');
      const type = String.fromCharCode(...bytes.subarray(start + 4, start + 8));
      let offset = -1;
      if (type === 'tkhd') {
        const version = bytes[start + 8];
        if (version > 1) throw new Error('Unsupported track header');
        offset = start + (version === 1 ? 28 : 20);
      } else if (type === 'trex' || type === 'tfhd') offset = start + 12;
      if (offset >= 0) {
        if (offset + 4 > start + size) throw new Error('Incomplete track header');
        if (view.getUint32(offset) === 0) view.setUint32(offset, 1);
      }
      if (['moov', 'trak', 'mvex', 'moof', 'traf'].includes(type)) walk(start + 8, start + size, depth + 1);
      start += size;
    }
  }
  walk(0, bytes.length);
  return bytes;
}
try {
  if (!state) {
    if (!request.first || typeof create !== 'function') throw new Error('Missing transmux session');
    state = {muxer: new create({remux: true, keepOriginalTimestamps: false}), audio: !!request.audio, init: null, output: [], bytes: 0};
    state.muxer.on('data', segment => {
      if (!segment.data?.byteLength) return;
      if (state.audio ? segment.type !== 'audio' : (!['combined', 'video'].includes(segment.type) ||
          !Number.isFinite(segment.info?.width) || !Number.isFinite(segment.info?.height) ||
          segment.info.width < 1 || segment.info.height < 1 ||
          segment.info.width > 16384 || segment.info.height > 16384))
        throw new Error('No supported video track');
      if (state.audio && (!Number.isFinite(segment.info?.samplerate) || segment.info.samplerate < 8000 ||
          segment.info.samplerate > 384000 || !Number.isInteger(segment.info.channelcount) ||
          segment.info.channelcount < 1 || segment.info.channelcount > 8)) throw new Error('Unsupported audio');
      const init = state.audio ? audioTrackIds(segment.initSegment) : segment.initSegment;
      const data = state.audio ? audioTrackIds(segment.data) : segment.data;
      if (!state.init) {
        state.init = new Uint8Array(init);
        state.output.push(state.init); state.bytes += state.init.byteLength;
      } else if (state.init.byteLength !== init.byteLength ||
                 state.init.some((byte, index) => byte !== init[index])) {
        throw new Error('Codec configuration changed');
      }
      state.output.push(data); state.bytes += data.byteLength;
      if (state.bytes > 16 * 1024 * 1024) throw new Error('Output limit exceeded');
    });
    registry.set(request.id, state);
  }
  if (state.audio !== !!request.audio) throw new Error('Track type changed');
  state.output = []; state.bytes = 0;
  if (typeof request.data !== 'string' || request.data.length > 12 * 1024 * 1024) throw new Error('Input limit exceeded');
  const binary = atob(request.data);
  const input = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; ++index) input[index] = binary.charCodeAt(index);
  state.muxer.push(input); state.muxer.flush();
  if (!state.bytes) throw new Error('No supported media frames');
  const chunks = [];
  for (const bytes of state.output) {
    for (let offset = 0; offset < bytes.length; offset += 16384)
      chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 16384)));
  }
  const data = btoa(chunks.join(''));
  state.output = []; state.bytes = 0;
  if (request.last) {state.muxer.dispose(); registry.delete(request.id);}
  return {ok: true, data};
} catch {
  state?.muxer?.dispose(); registry.delete(request.id);
  return {ok: false};
}
