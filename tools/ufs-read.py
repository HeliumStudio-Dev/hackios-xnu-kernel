#!/usr/bin/env python3
"""Read aligned bytes from a loader partition; writes only the host output file."""
import argparse
import hashlib
import fcntl
import os
from pathlib import Path
import re
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('partition')
p.add_argument('bytes', type=lambda s: int(s, 0))
p.add_argument('output', type=Path)
p.add_argument('--offset', type=lambda s: int(s, 0), default=0)
p.add_argument('--block-size', type=int, default=4096)
a = p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9_]{1,23}', a.partition):
    p.error('invalid partition name')
if a.block_size not in (512, 4096) or a.bytes <= 0 or a.offset < 0 or (a.bytes | a.offset) % a.block_size:
    p.error('offset and length must be positive/aligned to the block size')
if a.output.exists():
    p.error('output already exists')
digest = hashlib.sha256()
phone = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'hackios-phone'
with open(str(phone) + '.run', 'a') as run_lock, open(str(phone) + '.lock', 'a') as usb_lock, \
        tempfile.TemporaryDirectory(prefix='hackios-ufs-') as tmp:
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(usb_lock, fcntl.LOCK_EX)
    staged = Path(tmp) / 'chunk'
    with a.output.open('xb') as out:
        for at in range(0, a.bytes, 4 << 20):
            size = min(4 << 20, a.bytes - at)
            cmd = ['fastboot', 'oem', 'read-part', a.partition,
                   f'{(a.offset + at) // a.block_size:x}', f'{size // a.block_size:x}']
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            subprocess.run(['fastboot', 'get_staged', str(staged)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            data = staged.read_bytes()
            if len(data) != size:
                raise RuntimeError(f'short read at {at}: {len(data)} != {size}; output is incomplete')
            out.write(data)
            digest.update(data)
print(f'{digest.hexdigest()}  {a.output} ({a.bytes} bytes)')
