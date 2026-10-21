// request/create are supplied by the browser in its internal isolated world.
// The static source closure has no network/module-loader dependencies.
const registryKey = Symbol.for('internetBrowser.videoTransmuxers');
const registry = globalThis[registryKey] ||= new Map();
let state = registry.get(request.id);
try {
  if (!state) {
    if (!request.first || typeof create !== 'function') throw new Error('Missing transmux session');
    state = {muxer: new create({remux: true, keepOriginalTimestamps: false}), init: null, output: [], bytes: 0};
    state.muxer.on('data', segment => {
      if (!segment.data?.byteLength) return;
      if (!['combined', 'video'].includes(segment.type) ||
          !Number.isFinite(segment.info?.width) || !Number.isFinite(segment.info?.height) ||
          segment.info.width < 1 || segment.info.height < 1 ||
          segment.info.width > 16384 || segment.info.height > 16384)
        throw new Error('No supported video track');
      if (!state.init) {
        state.init = new Uint8Array(segment.initSegment);
        state.output.push(state.init); state.bytes += state.init.byteLength;
      } else if (state.init.byteLength !== segment.initSegment.byteLength ||
                 state.init.some((byte, index) => byte !== segment.initSegment[index])) {
        throw new Error('Codec configuration changed');
      }
      state.output.push(segment.data); state.bytes += segment.data.byteLength;
      if (state.bytes > 16 * 1024 * 1024) throw new Error('Output limit exceeded');
    });
    registry.set(request.id, state);
  }
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
