"""Assemble the sealed GA5 CT0 request from Git-sized binary parts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile


ROOT = Path(__file__).resolve().parent
CHUNK_SIZE = 48 * 2**20
BUFFER_SIZE = 2**20


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(BUFFER_SIZE), b''):
            digest.update(block)
    return digest.hexdigest()


def sha_field(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def assemble(destination):
    meta = json.loads((ROOT/'parts.json').read_bytes())
    fixture_bytes = (ROOT/'fixture.json').read_bytes()
    fixture = json.loads(fixture_bytes)
    if (meta['format'] != 'v32_ga5_ct0_split_v1'
            or hashlib.sha256(fixture_bytes).hexdigest() != meta['fixture_sha256']
            or fixture['format'] != 'v32_ga5_tiles_v1'
            or (fixture['layer'], fixture['scope'], fixture['ciphertexts'], fixture['raw_words'], len(fixture['tiles']))
            != ('g_a.5', 'ciphertext', 1, 60948480, 192)
            or fixture['request_sha256'] != meta['request_sha256']
            or fixture['request_bytes'] != meta['request_bytes']
            or fixture['request_bytes'] != 650142340):
        raise ValueError('unexpected G5 CT0 fixture identity')
    total = meta['request_bytes']
    parts = meta['parts']
    if len(parts) != (total+CHUNK_SIZE-1)//CHUNK_SIZE:
        raise ValueError('incorrect G5 CT0 part count')
    for index, part in enumerate(parts):
        size = min(CHUNK_SIZE,total-index*CHUNK_SIZE)
        if (part['name'],part['bytes']) != (f'part_{index:03}.part',size) or not sha_field(part['sha256']):
            raise ValueError(f'unsupported part entry {index}')

    if destination.is_symlink():
        raise ValueError('choose a regular output directory')
    if destination.exists():
        request = destination/'request.bin'
        existing = destination/'fixture.json'
        if (request.is_file() and not request.is_symlink() and existing.is_file() and not existing.is_symlink()
                and request.stat().st_size == total and sha256(request) == meta['request_sha256']
                and existing.read_bytes() == fixture_bytes):
            print(f'PASS_GA5_CT0_REUSED {destination}')
            return
        raise ValueError('output already exists with different data')
    if shutil.disk_usage(destination.parent).free < total+len(fixture_bytes):
        raise OSError('insufficient space for the assembled request')

    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='.ga5_ct0_',dir=destination.parent) as folder:
        staging = Path(folder)/'verified'
        staging.mkdir()
        with (staging/'request.bin').open('xb') as output:
            for index, part in enumerate(parts,1):
                path = ROOT/'parts'/part['name']
                if path.is_symlink() or not path.is_file() or path.stat().st_size != part['bytes']:
                    raise ValueError(f'missing or incorrect length for {part["name"]}')
                item_sha = hashlib.sha256()
                seen = 0
                with path.open('rb') as source:
                    for block in iter(lambda: source.read(BUFFER_SIZE), b''):
                        seen += len(block)
                        if seen > part['bytes']:
                            raise ValueError(f'{path.name} grew during copy')
                        item_sha.update(block)
                        digest.update(block)
                        output.write(block)
                if seen != part['bytes'] or item_sha.hexdigest() != part['sha256']:
                    raise ValueError(f'SHA-256 mismatch for {path.name}')
                print(f'PART_OK {index}/{len(parts)} {path.name}',flush=True)
        if digest.hexdigest() != meta['request_sha256']:
            raise ValueError('assembled request SHA-256 mismatch')
        (staging/'fixture.json').write_bytes(fixture_bytes)
        staging.rename(destination)
    print(f'PASS_GA5_CT0_ASSEMBLED {destination} bytes={total}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('ga5_full_ct0'))
    args = parser.parse_args()
    assemble(args.output.absolute())
