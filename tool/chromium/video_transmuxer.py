"""Bundle the pinned, unmodified mux.js source closure; no npm/runtime downloads."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re

ROOT = Path(__file__).resolve().parents[2]
REVISION = 'e1b4d161f51782e4712d020b66d5087bd6febb3d'


def bundle_transmuxer(directory: Path | None = None) -> str:
    directory = directory or ROOT / 'third_party/muxjs'
    record = json.loads((directory / 'provenance.json').read_text(encoding='utf-8'))
    if (record.get('upstream_commit') != REVISION or record.get('version') != '7.1.0'
            or record.get('license') != 'Apache-2.0' or record.get('external_modules') != []
            or record.get('github_source_files_verified') is not True):
        raise ValueError('Unexpected mux.js source provenance')
    sources = {}
    for name, expected in record['source_files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or not name.startswith('lib/') or not name.endswith('.js'):
            raise ValueError('Unexpected mux.js source path')
        data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('mux.js source bytes differ: ' + name)
        sources[name] = data.decode('utf-8')
    if len(sources) != 24 or 'lib/mp4/transmuxer.js' not in sources:
        raise ValueError('Incomplete mux.js source closure')
    mappings = {}
    for name, text in sources.items():
        dependencies = {}
        for dependency in re.findall(r"require\(['\"]([^'\"]+)['\"]\)", text):
            if not dependency.startswith('.'):
                raise ValueError('Unexpected external mux.js dependency')
            path = posixpath.normpath(posixpath.join(posixpath.dirname(name), dependency))
            target = next((path + suffix for suffix in ('', '.js', '/index.js') if path + suffix in sources), None)
            if target is None:
                raise ValueError('Incomplete mux.js relative dependency')
            dependencies[dependency] = target
        mappings[name] = dependencies
    factories = ',\n'.join(json.dumps(name) + ':function(module,exports,require){\n' + text + '\n}'
                            for name, text in sorted(sources.items()))
    return ('(() => {\n"use strict";\nconst factories={' + factories + '};\nconst dependencies=' +
            json.dumps(mappings, sort_keys=True) + ';\nconst cache=Object.create(null);\n'
            'function load(name){if(cache[name])return cache[name].exports;'
            'if(!Object.hasOwn(factories,name))throw new Error("Unknown media module");'
            'const module={exports:{}};cache[name]=module;'
            'factories[name](module,module.exports,key=>load(dependencies[name][key]));return module.exports;}\n'
            'return load("lib/mp4/transmuxer.js").Transmuxer;\n})()')


if __name__ == '__main__':
    print(bundle_transmuxer())
