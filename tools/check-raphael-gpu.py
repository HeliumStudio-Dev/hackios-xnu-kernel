#!/usr/bin/env python3
"""Run actual GMU parsing and PDC/RSC setup against RAM, never device registers."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / 'xnu/files/bsd/dev/hakios.adreno.c').read_text()

def function(name):
    return re.search(r'\n(?:static )?(?:bool|uint32_t)\n' + name + r'\([^;]*?\n\{.*?\n\}', src, re.S).group()

# Use the driver's own register offsets, with no independently maintained copy.
defines = '\n'.join(line for line in src.splitlines() if line.startswith('#define ') and
    re.match(r'#define (?:GCC_XO_DIV4_CBCR|PDC_|RSCC_|SMMU_|GMU_(?:WORD|ITCM|DTCM|CM3_SYSRESET|TCM_SIZE|FAILED|LOG_|HFI_ADDRESS|STREAM|MATCH|FIRMWARE_)|GPU_(?:CHIP_ID|ADDRESSES))', line))
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool a640;
static unsigned speed_bin, core_khz;
static uint64_t mach_absolute_time(void) { return 0; }
struct gmu_firmware_block { uint32_t address, size, type, value; };
static const uint8_t *gmu_firmware;
static uint64_t gmu_firmware_size;
struct block { const char *name; uint32_t phys, size; uintptr_t base; };
typedef uintptr_t vm_offset_t;
static struct block pdc, pdc_seq, rscc, gmu, smmu;
static uint32_t smmu_pages = 8, smmu_page = 4096;
struct gpu_block { uint64_t address, size; uintptr_t memory; };
static struct gpu_block gmu_blocks[12], gmu_log, gmu_hfi;
static struct gpu_space {
    const char *name;
    uint32_t context, control, table_count;
    struct { uint64_t phys; uint64_t *table; } tables[1];
} gmu_space = {.name = "the GMU", .context = 1};
static bool gmu_space_is_on;
static unsigned gmu_block_count, step = 14;
static char last_write[128];
#define PTE_GMU 0
#define PAGE_SIZE 16384
static bool block_new(struct gpu_space *space, struct gpu_block *block,
                      uint64_t address, uint32_t size, uint64_t attrs) {
    (void)space; (void)attrs;
    for (unsigned i = 0; i + 1 < gmu_block_count; i++)
        assert(address + size <= gmu_blocks[i].address ||
               address >= gmu_blocks[i].address + gmu_blocks[i].size);
    *block = (struct gpu_block){address, size, (uintptr_t)calloc(1, size)};
    return block->memory != 0;
}
static const uint8_t *image_file(const char *dir, const char *name, uint64_t *size) {
    assert(!strcmp(dir, "fw") && !strcmp(name, "a640_gmu.bin"));
    *size = gmu_firmware_size; return gmu_firmware;
}
static bool smmu_layout(void) { return true; }
static void to_memory(uintptr_t address, uint64_t size) { (void)address; (void)size; }
static uint32_t rd(uintptr_t at) { return *(uint32_t *)at; }
static void wr(uintptr_t at, uint32_t word) { *(uint32_t *)at = word; }
static bool wait_for(struct block *block, uint32_t off, uint32_t mask, uint32_t value, unsigned ms) {
    (void)ms; return (rd(block->base + off) & mask) == value;
}
static uint32_t regs[3][0x10000 / 4];
static uint32_t get(struct block *b, const char *name, uint32_t off) {
    (void)name; assert(!(off & 3) && off < 0x10000);
    if (b == &smmu) return rd(b->base + off);
    return regs[b == &pdc ? 0 : b == &pdc_seq ? 1 : 2][off / 4];
}
static void put(struct block *b, const char *name, uint32_t off, uint32_t value) {
    if (b == &gmu || b == &smmu) { assert(off < 0x30000); wr(b->base + off, value); return; }
    (void)name; assert(!(off & 3) && off < 0x10000);
    regs[b == &pdc ? 0 : b == &pdc_seq ? 1 : 2][off / 4] = value;
}
static bool ready = true, resources = true;
static bool cx_ready(void) { return ready; }
static void announce(const char *name) { (void)name; }
static uint32_t rpmh_resource(const char *name, void *levels, void *count) {
    (void)levels; (void)count;
    if (!resources) return 0;
    if (!strcmp(name, "mx.lvl")) return 0x30000;
    if (!strcmp(name, "cx.lvl")) return 0x30080;
    assert(!strcmp(name, "xo.lvl")); return 0x30028;
}
''' + defines + '\n' + '\n'.join(function(n) for n in
    ['in_tcm', 'gmu_block_read', 'gmu_has_failed', 'smmu_context', 'space_on',
     'step_gmu_space', 'step_gmu_firmware',
     'program_sequencers', 'hakios_gpu_parameter']) + r'''
int main(int argc, char **argv) {
    assert(argc == 2);
    FILE *f = fopen(argv[1], "rb"); assert(f);
    assert(!fseek(f, 0, SEEK_END)); long size = ftell(f); rewind(f); assert(size > 0);
    uint8_t *fw = malloc((size_t)size); assert(fw);
    assert(fread(fw, 1, (size_t)size, f) == (size_t)size); fclose(f);
    a640 = true;
    assert(GCC_XO_DIV4_CBCR == 0x43008);
    assert(!gmu_has_failed(0xbabeface) && gmu_has_failed(0));
    assert(in_tcm(0) && in_tcm(0x3fff) && in_tcm(0x40000) && in_tcm(0x43fff));
    assert(!in_tcm(0x4000) && !in_tcm(0x44000) && !in_tcm(0x10004000));
    gmu_firmware = fw; gmu_firmware_size = (uint64_t)size;
    uint64_t at = 0; unsigned blocks = 0;
    struct gmu_firmware_block block;
    while (at < gmu_firmware_size) {
        assert(gmu_block_read(&at, &block)); blocks++;
        assert(block.size);
        assert((block.address < 0x40000 && (uint64_t)block.address + block.size <= 0x40000) ||
               (block.address >= 0x40000 && (uint64_t)block.address + block.size <= 0x80000));
    }
    assert(blocks == 7 && at == gmu_firmware_size);
    gmu.base = (uintptr_t)calloc(1, 0x30000); assert(gmu.base);
    smmu.base = (uintptr_t)calloc(1, 0x10000); assert(smmu.base);
    assert(step_gmu_space() && gmu_space_is_on && gmu_block_count == 3);
    assert(rd(smmu.base + SMMU_SMR(1)) == 0x84000005);
    struct gpu_space core = {.name = "the 3D core"};
    assert(space_on(&core, 0, 0) && rd(smmu.base + SMMU_SMR(0)) == 0x84010000);
    a640 = false;
    assert(space_on(&core, 0, 0) && rd(smmu.base + SMMU_SMR(0)) == 0x84000000);
    a640 = true;
    assert(gmu_blocks[2].address == 0x60000000 && gmu_blocks[2].size == 4096);
    assert(step_gmu_firmware() && gmu_block_count == 3);
    for (at = 0; at < gmu_firmware_size;) {
        uint64_t data_at = at + sizeof(block);
        assert(gmu_block_read(&at, &block));
        if (in_tcm(block.address)) continue;
        unsigned i = block.address >= 0x40000;
        assert(!memcmp((void *)(gmu_blocks[i].memory + block.address - gmu_blocks[i].address),
                       fw + data_at, block.size));
    }
    for (unsigned i = 0; i < gmu_block_count; i++) free((void *)gmu_blocks[i].memory);
    free((void *)gmu_log.memory); free((void *)gmu_hfi.memory);
    free((void *)gmu.base);
    free((void *)smmu.base);
    at = 0; gmu_firmware_size = 15; assert(!gmu_block_read(&at, &block) && at == 0);
    gmu_firmware_size = 16; assert(!gmu_block_read(&at, &block));
    uint32_t bad[] = {0xfffffffc, 8, 0, 0, 0, 0};
    gmu_firmware = (const uint8_t *)bad; gmu_firmware_size = sizeof(bad);
    assert(!gmu_block_read(&at, &block)); bad[0] = 0; bad[1] = 3;
    assert(!gmu_block_read(&at, &block));
    assert(program_sequencers());
    assert(regs[1][0] == 0xfebea1e1 && regs[1][4] == 0x002081fc);
    assert(regs[0][0x1573] == 7 && regs[0][0x15d7] == 7);
    assert(regs[0][0x1576] == 0x30000 && regs[0][0x1577] == 1);
    assert(regs[0][0x15da + 4] == 0x30080 && regs[0][0x15db + 4] == 3);
    assert(regs[0][0x15da + 8] == 0x30028 && regs[0][0x15db + 8] == 3);
    assert(regs[2][0x180] == 0xa7a506a0 && regs[2][0x184] == 0x0020e8a8);
    assert(regs[2][0x12] == 0x80000000 && regs[0][0x1140] == 0x80000001);
    resources = false; assert(!program_sequencers()); resources = true;
    uint64_t value;
    assert(hakios_gpu_parameter(2, &value) && value == 1024 * 1024);
    assert(hakios_gpu_parameter(6, &value) && value == 0x100000);
    assert(hakios_gpu_parameter(3, &value) && value == 0x06040001);
    assert(hakios_gpu_parameter(0x10, &value) && value == 15);
    assert(hakios_gpu_parameter(0x13, &value) && value == 0);
    memset(regs, 0, sizeof(regs)); a640 = false;
    assert(GCC_XO_DIV4_CBCR == 0x6200c);
    assert(!gmu_has_failed(0x100) && gmu_has_failed(0xe00));
    assert(program_sequencers() && regs[1][0] == 0);
    assert(regs[2][0x180] == 0xeaaae5a0 && regs[2][0x12] == 0x80000021);
    assert(in_tcm(0x10004000) && !in_tcm(0x40000));
    assert(hakios_gpu_parameter(2, &value) && value == 512 * 1024);
    assert(hakios_gpu_parameter(6, &value) && value == 0);
    assert(hakios_gpu_parameter(3, &value) && value == 0x06030500);
    assert(hakios_gpu_parameter(0x13, &value) && value == 1);
    ready = false; assert(!program_sequencers());
    free(fw);
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-gpu-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(harness)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test'), str(root / 'fw-gpu/a640_gmu.bin')], check=True)
print('PASS: actual A640 firmware, malformed blocks, PDC/RSC and GPU parameters; 642L preserved (ASan/UBSan)')
