"""Build only the TGS app at the Pages root; leave existing repo pages untouched."""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time
import urllib.request

PDF_NAME = '2026_TGS_MAP_0914_EN.pdf'
PDF_URL = 'https://service.tgs.cesa.or.jp/files/96/tgs2026/map/' + PDF_NAME
PDF_SHA256 = '231244de5827b79da0af83f079a6f42c6b531695767bb5366c9a7d580729ccef'
EXPECTED_SIZE = (3827, 2232)
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tgs2026'
OUT = ROOT / '_site'


def valid_map(path: Path) -> bool:
    try:
        from PIL import Image
        data = path.read_bytes()
        if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
            return False
        if struct.unpack('<I', data[4:8])[0] + 8 != len(data):
            return False
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.size == EXPECTED_SIZE
    except (OSError, ValueError, struct.error):
        return False


def source_pdf() -> bytes:
    # A local copy lets a later build work even if the official URL is unavailable.
    local = ROOT / 'source' / PDF_NAME
    override = os.environ.get('TGS_SOURCE_PDF')
    if override:
        local = Path(override)
    if local.is_file():
        data = local.read_bytes()
    else:
        error = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(PDF_URL, headers={'User-Agent': 'TGS-personal-fieldguide-build/1.0'})
                with urllib.request.urlopen(req, timeout=25) as response:
                    data = response.read(20_000_001)
                if len(data) > 20_000_000:
                    raise ValueError('Official PDF exceeded expected download limit')
                break
            except Exception as exc:
                error = exc
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError('Cannot fetch official map. Add the original PDF as source/' + PDF_NAME + ' and rerun this workflow.') from error
    if hashlib.sha256(data).hexdigest() != PDF_SHA256:
        raise ValueError('Official PDF checksum differs from the uploaded 2026-09-14 map. Refusing to publish potentially mismatched coordinates.')
    return data


def rebuild_map(destination: Path) -> None:
    import fitz
    from PIL import Image
    data = source_pdf()
    with fitz.open(stream=data, filetype='pdf') as doc:
        if len(doc) != 1 or doc[0].rotation != 0:
            raise ValueError('Unexpected official map page layout')
        page = doc[0]
        if abs(page.rect.width - 8503.94043) > .1 or abs(page.rect.height - 4960.62988) > .1:
            raise ValueError('Official map page size changed')
        pixmap = page.get_pixmap(matrix=fitz.Matrix(.5, .5), alpha=False)
        image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
        image = image.resize(EXPECTED_SIZE, Image.Resampling.LANCZOS)
        image.save(destination, 'WEBP', quality=92, method=6)
    if not valid_map(destination):
        raise RuntimeError('Regenerated map failed WebP validation')


def main() -> None:
    scripts = [f'b{i:02d}.js' for i in range(14)] + ['games.js', 'facilities.js', 'app.js']
    required = ['index.html'] + scripts
    for name in required:
        path = SOURCE / name
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError('Missing application file: ' + str(path))
    for name in scripts:
        subprocess.run(['node', '--check', str(SOURCE / name)], check=True)
    # Check the data files in isolation without a browser or user localStorage.
    program = "const fs=require('fs'),vm=require('vm');let s='const B=[],G=[],F=[];';"
    program += "for(const f of " + json.dumps(scripts[:-1]) + ")s+=fs.readFileSync(f,'utf8')+';';"
    program += "s+='JSON.stringify({booths:B.length,games:G.length,facilities:F.length})';console.log(vm.runInNewContext(s,{}, {timeout:3000}));"
    result = subprocess.run(['node', '-e', program], cwd=SOURCE, check=True, capture_output=True, text=True)
    counts = json.loads(result.stdout)
    if counts['booths'] < 800 or counts['games'] < 40 or counts['facilities'] < 10:
        raise ValueError('Incomplete map/search data: ' + str(counts))
    OUT.mkdir(exist_ok=False)
    for name in required:
        shutil.copy2(SOURCE / name, OUT / name)
    if valid_map(SOURCE / 'map.webp'):
        shutil.copy2(SOURCE / 'map.webp', OUT / 'map.webp')
        repaired = False
    else:
        print('Stored map is missing or truncated; rebuilding from the checksum-verified official PDF.')
        rebuild_map(OUT / 'map.webp')
        repaired = True
    (OUT / '.nojekyll').touch()
    # Old /tgs2026/ bookmarks continue to reach the site root after this deployment.
    legacy = OUT / 'tgs2026'
    legacy.mkdir()
    (legacy / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=../"><title>TGS map</title><a href="../">Open TGS map</a>', encoding='utf-8')
    report = dict(counts, source=PDF_URL, source_sha256=PDF_SHA256, image_size=EXPECTED_SIZE,
                  image_bytes=(OUT / 'map.webp').stat().st_size, repaired_map=repaired,
                  commit=os.environ.get('GITHUB_SHA', 'local'))
    (OUT / 'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
