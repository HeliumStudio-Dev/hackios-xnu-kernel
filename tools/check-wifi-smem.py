#!/usr/bin/env python3
"""Run the actual SMEM allocator against a guarded fake shared heap and hardware lock."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
structs = source[source.index('struct smem_partition {'):source.index('/* An item found:')]
functions = '\n'.join(re.search(r'static bool\n' + name + r'\(.*?\n\}', source, re.S)[0]
                      for name in ('smem_item_make_locked', 'smem_item_make'))
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define SMEM_SIZE 65536u
#define SMEM_CANARY 0xa5a5
#define LOCK_US 1u
#define LOCK_OWNER 0
#define __offsetof offsetof
static unsigned step;
static char last_write[256];
static uint8_t heap[SMEM_SIZE];
static uint32_t owner, attempts, releases, ticks, publications, mutex_depth;
static int hakios_smem_alloc_lock;
static struct { uint32_t phys; uintptr_t base; } smem_lock = {0x1f43000, 0x1000};
static void quiet_print(const char *s, ...) { (void)s; }
#define printf quiet_print
static bool smem_peek(uint64_t at, void *out, uint32_t size) {
    assert(at + size <= sizeof(heap)); memcpy(out, heap + at, size); return true;
}
static uint32_t rd(uintptr_t at) { assert(at == smem_lock.base); return owner; }
static void wr(uintptr_t at, uint32_t value) {
    assert(at == smem_lock.base);
    if (value) { assert(value == LOCK_US && mutex_depth == 1); attempts++; if (!owner) owner = value; }
    else { assert(owner == LOCK_US); releases++; owner = 0; }
}
static uint32_t get(void *block, const char *name, unsigned at) {
    assert(block == &smem_lock && !strcmp(name, "owner") && at == 0); return owner;
}
static void smem_poke(uint32_t at, uint32_t value);
static void settle(void) { }
static void hold(bool fine) { (void)fine; }
static void sleep_ms(unsigned ms) { assert(ms == 1); ticks++; }
static void lck_mtx_lock(int *lock) { assert(lock == &hakios_smem_alloc_lock && mutex_depth == 0); mutex_depth++; }
static void lck_mtx_unlock(int *lock) { assert(lock == &hakios_smem_alloc_lock && mutex_depth == 1); mutex_depth--; }
''' + structs + r'''
static void smem_poke(uint32_t at, uint32_t value) {
    assert(owner == LOCK_US && mutex_depth == 1 && !(at & 3) && at <= sizeof(heap)-4);
    if (at == 64 + offsetof(struct smem_partition, free_uncached)) publications++;
    memcpy(heap + at, &value, 4);
}
''' + functions + r'''
static struct smem_partition *header(void) { return (void *)(heap + 64); }
static struct smem_entry *entry(unsigned at) { return (void *)(heap + 64 + at); }
static void reset(void) {
    memset(heap, 0xcc, sizeof(heap)); owner = attempts = releases = ticks = publications = mutex_depth = 0;
    *header() = (struct smem_partition){.magic="$PRT", .size=32768, .free_uncached=32, .free_cached=32768};
}
int main(void) {
    reset();
    assert(smem_item_make(64, 428, 340));
    assert(header()->free_uncached == 392 && publications == 1 && releases == 1 && !owner && !mutex_depth);
    assert(entry(32)->canary == SMEM_CANARY && entry(32)->item == 428 && entry(32)->size == 344 && entry(32)->padding_data == 4);
    assert(smem_item_make(64, 478, 32)); assert(smem_item_make(64, 479, 16384));
    assert(header()->free_uncached == 16840 && publications == 3);
    uint32_t old = header()->free_uncached;
    assert(smem_item_make(64, 428, 340) && header()->free_uncached == old && publications == 3);
    assert(!smem_item_make(64, 428, 341) && header()->free_uncached == old);
    assert(!smem_item_make(64, 480, 32768) && header()->free_uncached == old);
    assert(!smem_item_make(64, 480, 0)); assert(!smem_item_make(64, 480, UINT32_MAX));
    assert(!smem_item_make(UINT32_MAX, 480, 32)); assert(!owner && !mutex_depth);
    for (unsigned mode = 0; mode < 7; mode++) {
        reset();
        if (mode == 0) header()->magic[0] = 0;
        if (mode == 1) header()->size = SMEM_SIZE;
        if (mode == 2) header()->free_uncached = 31;
        if (mode == 3) header()->free_uncached = 32769;
        if (mode == 4) header()->free_cached = 32769;
        if (mode == 5) header()->free_uncached = 33;
        if (mode == 6) { header()->free_uncached = 48; *entry(32) = (struct smem_entry){SMEM_CANARY, 10, 0, 1, 0, 0}; }
        old = header()->free_uncached;
        assert(!smem_item_make(64, 428, 340) && header()->free_uncached == old && !publications);
        assert(releases == 1 && !owner && !mutex_depth);
    }
    reset(); header()->free_uncached = 64;
    *entry(32) = (struct smem_entry){SMEM_CANARY, 10, UINT32_MAX, 0, 0, 0};
    assert(!smem_item_make(64, 428, 340) && !owner && !publications);
    reset(); owner = 7; assert(!smem_item_make(64, 428, 340));
    assert(owner == 7 && attempts == 1001 && ticks == 1001 && releases == 0 && publications == 0 && !mutex_depth);
    puts("PASS: SMEM allocations, duplicates, bounds, corrupt entries and foreign lock timeout");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-smem-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-g', '-O1', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
