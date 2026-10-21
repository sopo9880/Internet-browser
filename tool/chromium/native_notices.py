"""Embed exact upstream notices, without changing their copyright text."""
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def license_page(android: bool = False) -> str:
    directory = ROOT / 'third_party/native-notices'
    entries = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    sections = []
    for entry in entries:
        if ('android' if android else 'windows') not in entry['platforms']:
            continue
        data = (directory / entry['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Upstream license notice hash differs: ' + entry['file'])
        sections.append('<section><h2>' + html.escape(entry['project']) + '</h2><p>' +
            html.escape(entry['file']) + ' · ' + html.escape(entry['revision']) +
            '</p><p><a href="' + html.escape(entry['repository'], quote=True) +
            '">원본 소스</a></p><pre>' + html.escape(data.decode('utf-8')) + '</pre></section>')
    return ('<!doctype html><html lang="ko"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>오픈소스 안내 · Internet Browser</title><link rel="stylesheet" href="style.css">'
            '<main><a href="index.html">← Internet Browser</a><h1>오픈소스 안내</h1>'
            '<p><a href="chrome://credits/">Chromium 전체 구성요소 안내</a> · '
            '<a href="https://github.com/sopo9880/Internet-browser">Internet Browser 소스</a></p>' +
            ''.join(sections) + '</main></html>')
