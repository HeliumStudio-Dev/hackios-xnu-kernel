#!/usr/bin/env python3
"""Check the actual SM8150 APCS and legacy IPCC doorbell routes."""
from pathlib import Path
import re
import subprocess
import tempfile
s = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f = re.search(r'static void\nring\(.*?\n\}', s, re.S)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef uintptr_t vm_offset_t;
#define IPCC_AOP 0
#define IPCC_WPSS 1
#define IPCC_SMP2P 2
#define IPCC_SEND 12
static unsigned maps, writes;
static uintptr_t written_at;
static uint32_t written_value;
static bool raphael;
static int ipcc;
static bool hakios_is_raphael(void) { return raphael; }
static uintptr_t ml_io_map(uintptr_t phys, unsigned size) {
    assert(phys == 0x17c00000 && size == 0x1000); maps++; return phys;
}
static void settle(void) { }
static void wr(uintptr_t at, uint32_t value) { written_at = at; written_value = value; writes++; }
static void put(void *p, const char *s, unsigned at, uint32_t value) {
    assert(p == &ipcc && s && at == IPCC_SEND); wr(0x408000 + at, value);
}
''' + f + r'''
int main(void) {
    raphael = true;
    ring(IPCC_AOP, 0, "AOP"); assert(written_at == 0x17c0000c && written_value == 1);
    ring(IPCC_WPSS, IPCC_SMP2P, "SMP2P"); assert(written_at == 0x17c0000c && written_value == (1u << 14));
    ring(IPCC_WPSS, 0, "GLINK"); assert(written_at == 0x17c0000c && written_value == (1u << 12));
    assert(maps == 1 && writes == 3);
    raphael = false; ring(IPCC_WPSS, IPCC_SMP2P, "legacy");
    assert(written_at == 0x40800c && written_value == (IPCC_WPSS << 16 | IPCC_SMP2P));
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-doorbell-') as tmp:
    p = Path(tmp)
    (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-fsanitize=address,undefined', str(p / 'check.c'), '-o', str(p / 'check')], check=True)
    subprocess.run([str(p / 'check')], check=True)
print('PASS: SM8150 AOP/SMP2P/GLINK APCS routes and legacy IPCC route')
