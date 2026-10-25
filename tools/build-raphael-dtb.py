#!/usr/bin/env python3
"""Build a complete raphael DTB from the local SM8150 downstream tree, without changing it."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('kernel', nargs='?', type=Path, default=Path.home() / 'kernel/zundamon_raphael')
ap.add_argument('-o', '--output', type=Path, default=Path(__file__).resolve().parents[1] / 'out/raphael/raphael.dtb')
args = ap.parse_args()
src = args.kernel.resolve()
dts = src / 'arch/arm64/boot/dts/qcom'
dtc = os.environ.get('DTC', str(src / 'out/scripts/dtc/dtc'))
merge = os.environ.get('FDTOVERLAY', str(src / 'out/scripts/dtc/fdtoverlay'))
output = args.output.resolve()
output.parent.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix='hackios-raphael-dtb-') as tmp:
    work = Path(tmp)
    with output.with_suffix('.build.log').open('w') as log:
        for name in ('sm8150-v2', 'raphael-sm8150-overlay'):
            pp = work / (name + '.dts')
            subprocess.run([os.environ.get('HOSTCC', 'gcc'), '-E', '-nostdinc', '-undef', '-D__DTS__',
                            '-x', 'assembler-with-cpp', '-I', str(src / 'scripts/dtc/include-prefixes'),
                            '-o', str(pp), str(dts / (name + '.dts'))], check=True)
            if name == 'raphael-sm8150-overlay':
                # Android's root metadata also needs a fragment when using libfdt's overlay merger.
                pp.write_text(re.sub(r'(?m)^(\s*)/\s*\{', r'\1&{/} {', pp.read_text()))
            subprocess.run([dtc, '-@', '-I', 'dts', '-O', 'dtb', '-b', '0', '-i', str(dts),
                            '-o', str(work / (name + '.dtb')), str(pp)], stderr=log, check=True)
        merged = work / 'raphael.dtb'
        subprocess.run([merge, '-i', str(work / 'sm8150-v2.dtb'), '-o', str(merged),
                        str(work / 'raphael-sm8150-overlay.dtb')], check=True)
        tree = subprocess.check_output([dtc, '-q', '-I', 'dtb', '-O', 'dts', str(merged)], text=True)
        # A base-only tree or a partially merged overlay is not a phone DTB.
        assert 'model = "RAPHAEL";' in tree
        assert 'qcom,board-id = <0x28 0x00>;' in tree
        assert '__fixups__ {' not in tree and '__local_fixups__ {' not in tree
        assert sorted(re.findall(r'\bcpu@([0-9a-f]+) \{\s*device_type = "cpu";', tree)) == ['0', '100', '200', '300', '400', '500', '600', '700']
        assert 'reg = <0x17a00000 0x10000 0x17a60000 0x100000>;' in tree
        assert 'reg = <0x00 0x9c000000 0x00 0x2400000>;' in tree
        assert 'method = "smc";' in tree and 'goodix_gt9886_cfg_f11.bin' in tree
        output.with_suffix('.dts').write_text(tree)
        output.write_bytes(merged.read_bytes())

revision = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip()
output.with_suffix('.source').write_text(f'{src}\n{revision}\n')
print(f'{output}: {output.stat().st_size} bytes; RAPHAEL, 8 CPUs, GICv3, SMC, GT9886 checked')
