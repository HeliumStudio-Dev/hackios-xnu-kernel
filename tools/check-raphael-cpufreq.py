#!/usr/bin/env python3
"""Exercise the actual SM8150 OSM LUT decoder without touching device registers."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnu/files/bsd/dev/hakios.cpufreq.c').read_text()
decoder = re.search(r'static bool\nosm_lut\(.*?\n\}', source, re.S)[0]
start = re.search(r'static void\nosm_start\(.*?\n\}', source, re.S)[0]
test = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define XO_KHZ 19200
#define ALTERNATE_KHZ 300000
''' + decoder + r'''
typedef uintptr_t vm_offset_t;
typedef void *thread_t;
typedef struct { unsigned num_cpus; struct { uint64_t phys_id; } cpus[8]; } ml_topology_info_t;
static ml_topology_info_t topology;
static uint32_t regs[3][0x1400/4], osm_saved[3], osm_low[3], osm_high[3], osm_row[3], osm_khz[3][40];
static const uint32_t osm_phys[3] = {0x18323000,0x18325800,0x18327800};
static vm_offset_t osm_base[3];
static bool osm_stopping, fail_thread;
static int osm_lock, mode;
static const ml_topology_info_t *ml_get_topology_info(void) { return &topology; }
static unsigned domain_of(uint64_t physical) { unsigned c = physical >> 8; return c < 4 ? 0 : c < 7 ? 1 : 2; }
static void PE_parse_boot_argn(const char *name, uint32_t *out, unsigned size) {
    assert(!strcmp(name,"cpufreq") && size == 4); *out = mode;
}
static void simple_lock_init(int *lock, int type) { (void)lock; (void)type; }
static vm_offset_t ml_io_map(uint32_t at, unsigned size) {
    assert(size == 0x1400);
    for (unsigned i = 0; i < 3; i++) if (at == osm_phys[i]) return (uintptr_t)regs[i];
    assert(0); return 0;
}
static void tell(const char *format, ...) { (void)format; }
static void osm_governor(void *arg, int result) { (void)arg; (void)result; }
#define KERN_SUCCESS 0
#define os_atomic_store(at,value,ordering) (*(at) = (value))
static int kernel_thread_start(void (*fn)(void *,int), void *arg, thread_t *out) {
    assert(fn == osm_governor && arg == NULL); *out = (void *)1; return fail_thread ? 1 : 0;
}
static void thread_set_thread_name(thread_t thread, const char *name) { assert(thread); (void)name; }
static void thread_deallocate(thread_t thread) { assert(thread); }
''' + start + r'''
static void test_start(unsigned requested, unsigned cores, bool fail) {
    memset(osm_base,0,sizeof(osm_base)); memset(regs,0,sizeof(regs));
    mode = requested; fail_thread = fail; osm_stopping = false;
    topology.num_cpus = cores;
    for (unsigned i = 0; i < cores; i++) topology.cpus[i].phys_id = (uint64_t)(7-i) << 8;
    for (unsigned d = 0; d < 3; d++) {
        regs[d][0] = 1; regs[d][0x920/4] = 3;
        regs[d][0x110/4] = 1u << 30 | 4u << 16 | 16;
        regs[d][(0x110+32)/4] = 1u << 30 | 4u << 16 | (50+d*50);
        regs[d][(0x110+64)/4] = regs[d][(0x110+32)/4];
    }
    osm_start();
    for (unsigned d = 0; d < 3; d++) {
        bool owned = cores == 7 || d == 2;
        if (requested == 2 || owned) {
            assert(osm_base[d] && osm_high[d] == 1 && osm_saved[d] == 3);
            assert(regs[d][0x920/4] == (fail ? 3 : 1));
            assert(osm_low[d] == (requested == 2 || (cores == 7 && d == 0) ? 1 : 0));
        } else assert(osm_base[d] == 0 && regs[d][0x920/4] == 3);
    }
    assert(osm_stopping == fail);
}
int main(void) {
    test_start(1,7,false); test_start(2,7,false); test_start(2,1,false);
    test_start(1,1,false); test_start(2,7,true);
    uint32_t entries[40] = {0}, khz[40] = {0}, low = 0, high = 0;
    entries[0] = 4u << 16;
    entries[1] = 1u << 30 | 4u << 16 | 50;
    entries[2] = 1u << 30 | 4u << 16 | 100;
    entries[3] = 1u << 30 | 1u << 16 | 150;
    entries[4] = entries[3];
    assert(osm_lut(entries, khz, &low, &high));
    assert(low == 0 && high == 2 && khz[1] == 960000 && khz[2] == 1920000);
    entries[3] = 1u << 30 | 4u << 16 | 150;
    entries[4] = entries[3];
    assert(osm_lut(entries, khz, &low, &high) && high == 3);
    memset(entries, 0, sizeof(entries));
    assert(!osm_lut(entries, khz, &low, &high));
    entries[0] = 1u << 30 | 4u << 16 | 255;
    entries[1] = entries[0];
    assert(!osm_lut(entries, khz, &low, &high));
    entries[0] = 1u << 30 | 4u << 16 | 100;
    entries[1] = 1u << 30 | 4u << 16 | 50;
    entries[2] = entries[1];
    assert(osm_lut(entries, khz, &low, &high) && low == 1 && high == 0);
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-osm-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
print('PASS: actual OSM LUT/start, adaptive/max modes, firmware-owned cores and startup rollback (ASan/UBSan)')
