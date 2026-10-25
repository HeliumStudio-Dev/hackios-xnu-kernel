#!/usr/bin/env python3
"""Extract the verified raphael XBL and apply byte-checked SM8150 firmware fixes."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'out/host-python'))
from uefi_firmware.uefi import FirmwareVolume, FirmwareFile, FirmwareFileSystemSection

source = root / 'out/raphael/firmware/xbl.img'
raw = source.read_bytes()
digest = hashlib.sha256(raw).hexdigest()
assert digest == '2feb056c7224ff5a1ed27fdbfc2e527f05db40b1ac7754684da17d34a821e043', 'validate patches for this XBL version first'
fv = FirmwareVolume(raw[raw.index(b'_FVH') - 40:])
assert fv.valid_header and fv.process()
out = root / 'Mu-Silicium/Binaries/raphael'
out.mkdir(parents=True, exist_ok=True)


def walk(obj):
    yield obj
    for child in obj.objects:
        if child is not None:
            yield from walk(child)


def sections(obj):
    for child in obj.objects:
        if child is None or isinstance(child, FirmwareFile):
            continue
        if isinstance(child, FirmwareFileSystemSection):
            yield child
        yield from sections(child)


records = []
types = {3: 'SEC', 4: 'PEI_CORE', 5: 'DXE_CORE', 6: 'PEIM', 7: 'DXE_DRIVER',
         9: 'UEFI_APPLICATION', 12: 'DXE_SMM_DRIVER'}
for f in (obj for obj in walk(fv) if isinstance(obj, FirmwareFile)):
    sec = list(sections(f))
    names = [s.name for s in sec if s.type == 0x15 and s.name]
    if f.type == 2 and names:
        data = next((s.data for s in sec if s.type == 0x19), None)
        if data is not None:
            name = Path(names[0].replace('\\', '/'))
            assert not name.is_absolute() and '..' not in name.parts
            dest = out / 'RawFiles' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    if f.type not in types:
        continue
    exe = next((s for s in sec if s.type in (0x10, 0x12)), None)
    if exe is None:
        continue
    code = exe.data
    if exe.type == 0x12:
        assert code[:2] == b'VZ' and struct.unpack_from('<H', code, 2)[0] == 0xaa64
    else:
        offset = struct.unpack_from('<I', code, 0x3c)[0]
        assert code[offset:offset + 4] == b'PE\0\0'
        assert struct.unpack_from('<H', code, offset + 4)[0] == 0xaa64
    paths = [p.decode().replace('\\', '/') for p in re.findall(rb'[a-zA-Z/\\0-9_\-\.]*\.dll\b', code)]
    pdb = next(p.split('/AARCH64/')[-1] for p in paths if '/AARCH64/' in p)
    parts = pdb.split('/')
    module, relative = parts[-3], Path(*parts[:-3])
    assert not relative.is_absolute() and '..' not in relative.parts
    dest = out / relative
    dest.mkdir(parents=True, exist_ok=True)
    (dest / (module + '.efi')).write_bytes(code)
    depex = next((s.data for s in sec if s.type in (0x13, 0x1b, 0x1c)), None)
    inf = (f'[Defines]\n  INF_VERSION = 0x0001001B\n  BASE_NAME = {module}\n'
           f'  FILE_GUID = {f.guid_label}\n  MODULE_TYPE = {types[f.type]}\n'
           f'  VERSION_STRING = 1.0\n\n[Binaries.AARCH64]\n'
           f'  {"TE" if exe.type == 0x12 else "PE32"}|{module}.efi|*\n')
    if depex is not None:
        (dest / (module + '.depex')).write_bytes(depex)
        inf += f'  DXE_DEPEX|{module}.depex|*\n'
    (dest / (module + '.inf')).write_text(inf)
    records.append({'name': module, 'inf': str(relative / (module + '.inf')),
                    'sha256': hashlib.sha256(code).hexdigest()})

# Derived from Project-Silicium/Device-Binaries cepheus at a1501e0; code matches this XBL.
patches = json.loads((root / 'devices/raphael/uefi/raphael-firmware-patches.json').read_text())
for patch in patches:
    matches = list(out.glob('**/' + patch['module'] + '.efi'))
    assert len(matches) == 1, patch['module']
    dest = matches[0]
    code = bytearray(dest.read_bytes())
    assert hashlib.sha256(code).hexdigest() == patch['original_sha256'], dest
    for offset, old, new in patch['changes']:
        assert code[offset] == old, (dest, offset)
        code[offset] = new
    assert hashlib.sha256(code).hexdigest() == patch['patched_sha256'], dest
    dest.write_bytes(code)
(out / 'manifest.json').write_text(json.dumps({'xbl_sha256': digest, 'modules': records}, indent=2) + '\n')
(out / 'patches.json').write_text(json.dumps(patches, indent=2) + '\n')
print(f'{len(records)} AArch64 modules extracted; DAL/USB/buttons patches verified')
