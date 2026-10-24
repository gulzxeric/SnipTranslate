"""Create the portable Windows release with bilingual docs and dependency notices."""
from __future__ import annotations

from collections import deque
from hashlib import file_digest
from importlib import metadata
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from screen_translate import __version__


def dependencies():
    pending = deque(['pyinstaller'])
    for line in (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            requirement = Requirement(line)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
    found = {}
    while pending:
        distribution = metadata.distribution(pending.popleft())
        key = distribution.metadata['Name'].lower().replace('_', '-')
        if key in found:
            continue
        found[key] = distribution
        for value in distribution.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                pending.append(requirement.name)
    return found


def package():
    application = ROOT / 'dist' / 'SnipTranslate'
    required = ['SnipTranslate.exe', '_internal/rapidocr/models/PP-OCRv6_det_small.onnx',
                '_internal/rapidocr/models/PP-OCRv6_rec_small.onnx']
    for relative in required:
        if not (application / relative).is_file():
            raise RuntimeError(f'Missing release file: {relative}. Run build.ps1 first.')
    target = ROOT / 'dist' / 'releases'
    target.mkdir(parents=True, exist_ok=True)
    archive = target / f'SnipTranslate-v{__version__}-windows-x64.zip'
    notices = [
        '# Third-party notices / 第三方组件说明', '',
        'The following runtime and packaging components retain their own licenses.',
        '以下运行与打包组件保留各自的许可，原始许可文件随压缩包附带。', '',
        'Snipaste is not included. / 本压缩包不包含 Snipaste。', '',
        '## Components / 组件', '',
    ]
    versions = {}
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(application.rglob('*')):
            if path.is_file() and not path.name.endswith('.excluded'):
                bundle.write(path, 'SnipTranslate/' + path.relative_to(application).as_posix())
        for name in ['README.md', 'README.en.md', 'RELEASE_NOTES.md']:
            bundle.write(ROOT / name, 'SnipTranslate/' + name)
        python_license = Path(sys.base_prefix) / 'LICENSE.txt'
        if not python_license.is_file():
            raise RuntimeError('Python LICENSE.txt is required for this Windows release.')
        bundle.write(python_license, 'SnipTranslate/licenses/Python/LICENSE.txt')
        notices += [f'- Python {sys.version.split()[0]}: https://www.python.org/', '']
        for name, distribution in sorted(dependencies().items()):
            info = distribution.metadata
            versions[info['Name']] = distribution.version
            license_name = info.get('License-Expression') or info.get('License') or 'See bundled license files'
            if len(license_name) > 200 or '\n' in license_name:
                license_name = 'See bundled license files'
            urls = info.get_all('Project-URL') or []
            sources = [value.partition(',')[2].strip() for value in urls]
            if info.get('Home-page'):
                sources.append(info['Home-page'])
            notices.append(f'- **{info["Name"]} {distribution.version}** — {license_name}')
            notices.extend(f'  - {url}' for url in dict.fromkeys(sources) if url.startswith('https://'))
            for file in distribution.files or []:
                relative = Path(str(file))
                upper = relative.name.upper()
                if '..' in relative.parts:
                    continue
                if not ('licenses' in [part.lower() for part in relative.parts]
                        or upper.startswith(('LICENSE', 'COPYING', 'NOTICE', 'COPYRIGHT'))):
                    continue
                source = distribution.locate_file(file)
                if source.is_file():
                    bundle.write(source, f'SnipTranslate/licenses/{name}/{relative.as_posix()}')
        # Include the open-source Qt license texts alongside the wheel's
        # licensing alternatives, and the upstream OCR model project notice.
        qt_version = metadata.version('PySide6-Essentials')
        upstream = {
            'Qt/LGPL-3.0-only.txt': f'https://raw.githubusercontent.com/qt/qtbase/v{qt_version}/LICENSES/LGPL-3.0-only.txt',
            'Qt/GPL-3.0-only.txt': f'https://raw.githubusercontent.com/qt/qtbase/v{qt_version}/LICENSES/GPL-3.0-only.txt',
            'PaddleOCR/LICENSE': 'https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE',
        }
        for name, url in upstream.items():
            with urlopen(url, timeout=30) as response:
                bundle.writestr('SnipTranslate/licenses/' + name, response.read())
        notices += ['', '## Qt and OCR model sources / Qt 与 OCR 模型来源', '',
            f'- Qt: https://code.qt.io/cgit/qt/qtbase.git/ (v{qt_version})',
            f'- PySide6 / Shiboken: https://code.qt.io/cgit/pyside/pyside-setup.git/ (v{qt_version})',
            f'- RapidOCR: https://github.com/RapidAI/RapidOCR (v{metadata.version("rapidocr")})',
            '- PaddleOCR models: https://github.com/PaddlePaddle/PaddleOCR',
            '- Included models: PP-OCRv6_det_small.onnx, PP-OCRv6_rec_small.onnx.', '',
            'Qt libraries are dynamically loaded from _internal and may be replaced with compatible builds.',
            'Qt 动态库位于 _internal，可替换为兼容构建。', '']
        text = '\n'.join(notices)
        bundle.writestr('SnipTranslate/THIRD_PARTY_NOTICES.md', text)
        manifest = {'application': 'SnipTranslate', 'version': __version__,
                    'platform': 'windows-x64', 'python': sys.version.split()[0], 'dependencies': versions}
        bundle.writestr('SnipTranslate/release-manifest.json', json.dumps(manifest, indent=2))
    (target / 'THIRD_PARTY_NOTICES.md').write_text(text, encoding='utf-8')
    with archive.open('rb') as stream:
        digest = file_digest(stream, 'sha256').hexdigest()
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size,
                      'sha256': digest, 'checksum': str(checksum)}, indent=2))


if __name__ == '__main__':
    package()
