"""Real-media checks for the native fragmented MP4 muxer (video_mux.h).

Generates H.264 video-only and AAC audio-only fragmented MP4 inputs with
ffmpeg in the layouts the saver produces (ffmpeg fragments with relative and
absolute base offsets, concatenated DASH segments, and mux.js output for
MPEG-TS input as used by YouTube HLS), muxes them with the compiled
video_mux_check binary and verifies with ffprobe/ffmpeg that:
  - the output has exactly one H.264 and one AAC stream,
  - it decodes without errors,
  - every decoded video and audio frame is bit-identical to its input,
  - seeking into the middle works.

Usage: python3 tool/tests/video_mux_media_test.py PATH_TO_video_mux_check
Skips (exit 0) when ffmpeg/ffprobe or node are unavailable.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECONDS = 6


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def ffmpeg(*args):
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args)


def video_source():
    return ['-f', 'lavfi', '-i', f'testsrc2=size=320x240:rate=30:duration={SECONDS}',
            '-c:v', 'libx264', '-preset', 'veryfast', '-g', '30', '-pix_fmt', 'yuv420p', '-an']


def audio_source(rate=48000):
    return ['-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate={rate}:duration={SECONDS}',
            '-c:a', 'aac', '-b:a', '96k', '-vn']


def fragmented(work, absolute):
    flags = '+frag_keyframe+empty_moov' + ('' if absolute else '+default_base_moof')
    video, audio = work / 'v.mp4', work / 'a.mp4'
    ffmpeg(*video_source(), '-movflags', flags, str(video))
    ffmpeg(*audio_source(44100), '-movflags', flags, '-frag_duration', '1000000', str(audio))
    return video, audio


def dash(work):
    """init + every media segment concatenated, exactly as the saver appends parts."""
    def build(name, source):
        folder = work / name
        folder.mkdir()
        ffmpeg(*source, '-f', 'dash', '-seg_duration', '1', '-use_template', '1',
               '-use_timeline', '1', '-init_seg_name', 'init.m4s',
               '-media_seg_name', 'chunk-$Number%05d$.m4s', str(folder / 'manifest.mpd'))
        output = work / f'{name}.mp4'
        with output.open('wb') as out:
            out.write((folder / 'init.m4s').read_bytes())
            for chunk in sorted(folder.glob('chunk-*.m4s')):
                out.write(chunk.read_bytes())
        return output
    return build('dash-v', video_source()), build('dash-a', audio_source())


TRANSMUX = r"""
const fs = require('node:fs'), vm = require('node:vm');
const [factory, script, input, output, audio] = process.argv.slice(2);
const context = vm.createContext({atob, btoa});
const data = fs.readFileSync(input);
// Split into TS packets the way HLS parts arrive (several parts per stream).
const parts = [];
const size = 188 * 2000;
for (let offset = 0; offset < data.length; offset += size) parts.push(data.subarray(offset, offset + size));
const chunks = [];
parts.forEach((part, index) => {
  const request = {id: 'mux-test', audio: audio === '1', first: index === 0, last: index === parts.length - 1,
                   data: part.toString('base64')};
  const result = vm.runInContext(`(() => {const request=${JSON.stringify(request)}; const create=${
      index === 0 ? fs.readFileSync(factory, 'utf8') : 'null'};\n${fs.readFileSync(script, 'utf8')}\n})()`, context);
  if (!result.ok) throw new Error('transmux failed at part ' + index);
  chunks.push(Buffer.from(result.data, 'base64'));
});
fs.writeFileSync(output, Buffer.concat(chunks));
"""


def muxjs(work):
    factory = work / 'factory.js'
    factory.write_text(run(sys.executable, '-X', 'utf8', '-m', 'tool.chromium.video_transmuxer', cwd=ROOT).stdout)
    script = ROOT / 'native/chromium/windows/resources/video_transmuxer.js'
    runner = work / 'transmux.cjs'
    runner.write_text(TRANSMUX)
    ts_video, ts_audio = work / 'v.ts', work / 'a.ts'
    ffmpeg(*video_source(), '-bsf:v', 'h264_mp4toannexb', '-f', 'mpegts', str(ts_video))
    ffmpeg(*audio_source(), '-f', 'mpegts', str(ts_audio))
    outputs = []
    for source, name, audio in ((ts_video, 'muxjs-v.mp4', '0'), (ts_audio, 'muxjs-a.mp4', '1')):
        output = work / name
        run('node', str(runner), str(factory), str(script), str(source), str(output), audio)
        outputs.append(output)
    return tuple(outputs)


def streams(path):
    data = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)).stdout)
    return data['streams'], float(data['format'].get('duration', 0))


def frame_hashes(path, selector):
    lines = run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(path), '-map', selector,
                '-f', 'framemd5', '-').stdout.splitlines()
    return [line.rsplit(',', 1)[1].strip() for line in lines if line and not line.startswith('#')]


def check(name, binary, video, audio, work):
    output = work / f'{name}-muxed.mp4'
    result = subprocess.run([binary, str(video), str(audio), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, f'{name}: {result.stderr}'
    found, duration = streams(output)
    kinds = sorted((s['codec_type'], s['codec_name']) for s in found)
    assert kinds == [('audio', 'aac'), ('video', 'h264')], f'{name}: {kinds}'
    assert abs(duration - SECONDS) < 0.5, f'{name}: duration {duration}'
    errors = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(output), '-f', 'null', '-'],
                            capture_output=True, text=True).stderr
    assert not errors.strip(), f'{name}: decode errors: {errors}'
    for selector in ('0:v', '0:a'):
        original = frame_hashes(video if selector == '0:v' else audio, selector)
        merged = frame_hashes(output, selector)
        assert original and merged == original, f'{name}: {selector} frames differ ({len(original)} vs {len(merged)})'
    seek = run('ffprobe', '-v', 'error', '-read_intervals', '4%+0.5', '-select_streams', 'v',
               '-show_entries', 'frame=pts_time', '-of', 'csv=p=0', str(output)).stdout.split()
    assert seek and 3.5 <= float(seek[0]) <= 4.6, f'{name}: seek landed at {seek[:1]}'
    print(f'ok - {name}: H.264 + AAC, {len(merged)} audio frames identical, seek to {float(seek[0]):.2f}s')


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    missing = [tool for tool in ('ffmpeg', 'ffprobe', 'node') if not shutil.which(tool)]
    if missing:
        print(f'SKIP video mux media test: {", ".join(missing)} not installed')
        return
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for name, build in (('fragmented-relative', lambda w: fragmented(w, False)),
                            ('fragmented-absolute', lambda w: fragmented(w, True)),
                            ('dash-segments', dash),
                            ('muxjs-ts', muxjs)):
            folder = work / name
            folder.mkdir()
            video, audio = build(folder)
            check(name, binary, video, audio, folder)
    print('Real-media fragmented MP4 mux checks passed.')


if __name__ == '__main__':
    main()
