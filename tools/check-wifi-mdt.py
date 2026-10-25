#!/usr/bin/env python3
"""Exercise the actual DSP image parser with WPSS and 33-segment MPSS headers."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
declarations = source[source.index('#define MDT_HASH'):source.index('static bool\nstep_firmware(')]
function = re.search(r'static bool\nstep_firmware\(.*?\n\}', source, re.S)[0]
copies = '\n'.join(re.search(r'static (?:uint64_t|bool)\n' + name + r'\(.*?\n\}', source, re.S)[0]
                   for name in ('segment_word', 'step_image'))
test = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PAGE_SIZE 16384
static unsigned step;
static void quiet_print(const char *format, ...) { (void)format; }
#define printf quiet_print
static uint32_t WPSS_MEMORY, WPSS_MEMORY_SIZE;
static const char *dsp_image_name;
static uint8_t header[PAGE_SIZE + 1], contents[64][64];
static uint64_t header_bytes;
static int missing = -1, wrong_size = -1;
static void announce(const char *s) { (void)s; }
static const uint8_t *image_file(const char *name, uint64_t *size) {
    char expected[32]; snprintf(expected, sizeof(expected), "%s.mdt", dsp_image_name);
    if (!strcmp(name, expected)) { *size = header_bytes; return header; }
    for (unsigned i = 0; i < 64; i++) {
        snprintf(expected, sizeof(expected), "%s.b%02u", dsp_image_name, i);
        if (!strcmp(name, expected)) {
            if ((int)i == missing) return NULL;
            *size = (int)i == wrong_size ? 15 : 16; return contents[i];
        }
    }
    assert(0); return NULL;
}
''' + declarations + '\n' + function + r'''
typedef uintptr_t vm_offset_t;
#define VM_WIMG_WCOMB 0
static uint64_t memory[16];
static unsigned unmapped;
static bool image_written, map_fail;
static char last_write[256];
static uintptr_t ml_io_map_unmappable(uint32_t physical, uint32_t size, int mode) {
    assert(physical == WPSS_MEMORY && size == sizeof(memory) && mode == VM_WIMG_WCOMB);
    return map_fail ? 0 : (uintptr_t)memory;
}
static void ml_io_unmap(uintptr_t at, uint32_t size) {
    assert(at == (uintptr_t)memory && size == sizeof(memory)); unmapped++;
}
static void hold(bool fine) { (void)fine; }
static void settle(void) { }
''' + copies + r'''
static struct elf_segment *ph(unsigned i) { return (void *)(header + 52 + 32 * i); }
static void prepare(unsigned count, bool mpss) {
    dsp_image_name = mpss ? "modem" : "wpss";
    WPSS_MEMORY = mpss ? 0x8e000000 : 0x9ae00000;
    WPSS_MEMORY_SIZE = mpss ? 0x09600000 : 0x01900000;
    memset(header, 0, sizeof(header)); memcpy(header, "\177ELF\1\1", 6);
    header[28] = 52; header[42] = 32; header[44] = count;
    header_bytes = 52 + 32 * count + 32;
    missing = wrong_size = -1;
    ph(1)->flags = 2u << 24; ph(1)->file_size = 32;
    for (unsigned i = 2; i < count; i++) {
        *ph(i) = (struct elf_segment){.type = 1, .paddr = WPSS_MEMORY + (i - 2) * 0x1000,
            .file_size = 16, .memory_size = 32, .flags = 0x08000006};
    }
}
int main(void) {
    for (unsigned mpss = 0; mpss < 2; mpss++) {
        unsigned count = mpss ? 33 : 8;
        prepare(count, mpss); assert(step_firmware()); assert(image.segments == count - 2);
        assert(image.size == (count - 2) * 4096 && image.header_size == header_bytes);
        for (unsigned n = 0; n < 52; n++) { prepare(count, mpss); header_bytes = n; assert(!step_firmware()); }
        prepare(count, mpss); header[4] = 2; assert(!step_firmware());
        prepare(count, mpss); header[5] = 2; assert(!step_firmware());
        prepare(count, mpss); header[28] = 64; assert(!step_firmware());
        prepare(count, mpss); header[42] = 16; assert(!step_firmware());
        prepare(count, mpss); header[44] = 65; assert(!step_firmware());
        prepare(count, mpss); header[44] = 2; assert(!step_firmware());
        prepare(count, mpss); header_bytes = 52 + 32 * count - 1; assert(!step_firmware());
        prepare(count, mpss); header_bytes = PAGE_SIZE + 1; assert(!step_firmware());
        prepare(count, mpss); ph(2)->file_size = 33; assert(!step_firmware());
        prepare(count, mpss); ph(2)->paddr--; assert(!step_firmware());
        prepare(count, mpss); ph(3)->paddr = WPSS_MEMORY + WPSS_MEMORY_SIZE - 16; assert(!step_firmware());
        prepare(count, mpss); ph(3)->paddr = 0xfffffff0; assert(!step_firmware());
        prepare(count, mpss); missing = 3; assert(!step_firmware());
        prepare(count, mpss); wrong_size = 3; assert(!step_firmware());
        prepare(count, mpss); ph(1)->file_size++; assert(!step_firmware());
        prepare(count, mpss); ph(2)->file_size = 0; missing = 2; assert(step_firmware());
        assert(image.segment[0].file == NULL && image.segment[0].memory_size == 32);
    }
    prepare(64, true); assert(step_firmware()); assert(image.segments == 62);
    WPSS_MEMORY_SIZE = sizeof(memory); image.segments = 2;
    for (unsigned i = 0; i < sizeof(contents[2]); i++) contents[2][i] = (uint8_t)(i + 1);
    for (unsigned bytes = 0; bytes <= 45; bytes++) {
        memset(memory, 0xa5, sizeof(memory)); unmapped = 0;
        image.segment[0].at = 0; image.segment[0].file_size = bytes;
        image.segment[0].memory_size = 45; image.segment[0].file = bytes ? contents[2] : NULL;
        image.segment[1].at = 64; image.segment[1].file_size = 13;
        image.segment[1].memory_size = 17; image.segment[1].file = contents[2];
        assert(step_image() && image_written && unmapped == 1);
        uint8_t *p = (void *)memory;
        for (unsigned i = 0; i < 45; i++) assert(p[i] == (i < bytes ? i + 1 : 0));
        for (unsigned i = 45; i < 64; i++) assert(p[i] == 0xa5);
        for (unsigned i = 64; i < 81; i++) assert(p[i] == (i < 77 ? i - 63 : 0));
        for (unsigned i = 81; i < sizeof(memory); i++) assert(p[i] == 0xa5);
    }
    image.segment[0].at = 1; unmapped = 0; assert(!step_image() && unmapped == 1);
    map_fail = true; unmapped = 0; assert(!step_image() && unmapped == 0);
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-mdt-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True, stdout=subprocess.DEVNULL)
print('PASS: actual WPSS/MPSS parser and copy, ELF bounds, missing files, zero-fill and byte tails (ASan/UBSan)')
