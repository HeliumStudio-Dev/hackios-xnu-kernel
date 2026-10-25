#!/usr/bin/env python3
"""Check raphael's UEFI allocator against the running phone's Recovery FDT."""
import argparse
from pathlib import Path
import re
import os
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('fdt', nargs='?', type=Path, default=root / 'out/raphael/firmware/recovery.dtb')
ap.add_argument('--map', type=Path, default=root / 'devices/raphael/uefi/files/Platforms/Xiaomi/raphaelPkg/Library/MemoryMapLib/MemoryMapLib.c')
args = ap.parse_args()
dtc = os.environ.get('DTC') or shutil.which('dtc') or str(Path.home() / 'kernel/zundamon_raphael/out/scripts/dtc/dtc')
tree = subprocess.check_output([str(dtc), '-q', '-I', 'dtb', '-O', 'dts', str(args.fdt)], text=True)


def ranges(body):
    reg = re.search(r'\breg = <([^>]+)>;', body)
    assert reg, 'missing physical memory range'
    cells = [int(x, 16) for x in reg[1].split()]
    assert len(cells) % 4 == 0
    return [(a << 32 | b, (a << 32 | b) + (c << 32 | d))
            for a, b, c, d in zip(cells[::4], cells[1::4], cells[2::4], cells[3::4])]


banks = ranges(re.search(r'\n\tmemory \{(.*?)\n\t\};', tree, re.S)[1])
reserved = []
body = re.search(r'\n\treserved-memory \{(.*?)\n\t\};', tree, re.S)[1]
for name, props in re.findall(r'\n\t\t([^{}\n]+) \{([^{}]*)\};', body):
    if re.search(r'\breg = ', props):
        reserved.extend((a, b, name) for a, b in ranges(props))

regions = []
for line in args.map.read_text().splitlines():
    match = re.search(r'\{"([^"]+)",\s*(0x[\da-fA-F]+),\s*(0x[\da-fA-F]+),\s*(.*)\}', line)
    if match:
        name, address, length, flags = match.groups()
        a, size = int(address, 16), int(length, 16)
        if a >= 0x80000000:
            regions.append((a, a + size, name, flags))
regions.sort()
assert regions, 'empty UEFI map'
for left, right in zip(regions, regions[1:]):
    assert left[1] <= right[0], f'UEFI regions overlap: {left[2]}, {right[2]}'
for a, b, name, flags in regions:
    if re.search(r'\b(?:Conv|BsData|BsCode)\b', flags):
        assert any(x <= a < b <= y for x, y in banks), f'{name} outside physical RAM'
        for x, y, owner in reserved:
            assert b <= x or a >= y, f'{name} overlaps Recovery reservation {owner}'
heap = next(x for x in regions if x[2] == 'DXE Heap')
assert heap[1] - heap[0] >= 0x08000000, 'DXE heap too small for this firmware'
stack = next(x for x in regions if x[2] == 'UEFI Stack')
dsc = (root / 'devices/raphael/uefi/files/Platforms/Xiaomi/raphaelPkg/raphael.dsc').read_text()
assert int(re.search(r'PcdCPUCoresStackBase\|(0x[\da-fA-F]+)', dsc)[1], 16) == stack[0]
assert int(re.search(r'PcdCPUCorePrimaryStackSize\|(0x[\da-fA-F]+)', dsc)[1], 16) == stack[1] - stack[0]
timer = re.search(r'compatible = "arm,armv8-timer";\s*interrupts = <([^>]+)>;', tree)
assert timer, 'missing architectural timer interrupts'
irqs = [int(x, 16) for x in timer[1].split()]
assert len(irqs) >= 9 and irqs[6] == 1, 'virtual timer must use a GIC PPI'
expected_irq = 16 + irqs[7]
profile = (root / 'devices/raphael/device.conf').read_text()
assert int(re.search(r'gic_timer_irq=(\d+)', profile)[1]) == expected_irq, 'profile uses the wrong timer IRQ'
print(f'UEFI map: {len(regions)} RAM regions, {len(reserved)} Recovery reservations; allocator/stack checked; virtual timer PPI {expected_irq}')
