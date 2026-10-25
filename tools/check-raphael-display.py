#!/usr/bin/env python3
"""Exercise scanout rotation and timeout rollback against RAM, not DPU registers."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnu/files/bsd/dev/hakios.adreno.c').read_text()
functions = []
for name in ['raphael_display_back', 'raphael_display_scan_counter', 'raphael_display_present', 'raphael_display_quiesce']:
    f = re.search(r'(?:void \*|void|bool|int)\n' + name + r'\(.*?\n\}', source, re.S)[0]
    functions.append(f.replace('__asm__ volatile ("dsb sy" ::: "memory");',
                               '__atomic_thread_fence(__ATOMIC_SEQ_CST);'))
test = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#define NSEC_PER_MSEC 1000000ull
#define NSEC_PER_USEC 1000ull
static uint32_t regs[0x85000/4], te[0x400/4];
static uint32_t gcc_regs[0xc000/4], dispcc_regs[0x3000/4];
static struct { vm_offset_t base; } gcc;
#define CBCR_OFF (1u << 31)
static vm_offset_t raphael_dispcc;
static uint8_t pixels[3][16];
static vm_offset_t raphael_mdp, raphael_te, raphael_irq, raphael_fb[3];
static uint32_t raphael_front, raphael_back = 1, raphael_fb_size = 16;
static bool raphael_flipping = true, latch = true;
static uint64_t loader_framebuffer, now;
static void loader_set_framebuffer(uint64_t pa) { loader_framebuffer = pa; }
static uint32_t rd(uintptr_t at) { return *(uint32_t *)at; }
static void wr(uintptr_t at, uint32_t v) {
    if (at == raphael_irq + 8) *(uint32_t *)(raphael_irq + 4) &= ~v;
    else *(uint32_t *)at = v;
}
static uint64_t mach_absolute_time(void) { return now; }
static void absolutetime_to_nanoseconds(uint64_t t, uint64_t *ns) { *ns = t; }
static void delay_for_interval(unsigned interval, uint64_t scale) {
    now += interval * scale;
    if (latch) { te[0x4/4] |= 1u << 3; regs[0x2018/4] = 0; }
}
void raphael_display_quiesce(void);
''' + '\n'.join(functions) + r'''
int main(void) {
    raphael_mdp = (uintptr_t)regs; raphael_te = (uintptr_t)te; raphael_irq = (uintptr_t)te;
    gcc.base = (uintptr_t)gcc_regs; raphael_dispcc = (uintptr_t)dispcc_regs;
    uint32_t phase = 99;
    assert(!raphael_display_scan_counter(&phase) && phase == 99);
    gcc_regs[0xb00c/4] = 1; te[0x284/4] = 1; te[0x288/4] = 3u << 19;
    te[0x294/4] = 2340; te[0x298/4] = 2340 + 500;
    te[4/4] = 1u << 3;
    assert(raphael_display_scan_counter(&phase) && phase == 500 && te[4/4] == 1u << 3);
    te[0x298/4] = 0;
    assert(raphael_display_scan_counter(&phase) && phase == ((0u - 2340) & 0xffff));
    dispcc_regs[0x2080/4] = CBCR_OFF;
    assert(!raphael_display_scan_counter(&phase)); dispcc_regs[0x2080/4] = 0;
    te[0x288/4] = 1u << 19;
    assert(!raphael_display_scan_counter(&phase)); te[0x288/4] = 3u << 19;
    for (unsigned i = 0; i < 3; i++) raphael_fb[i] = (uintptr_t)pixels[i];
    memset(pixels[0], 7, sizeof(pixels[0]));
    te[0x2b4/4] = 0x80000001;
    for (unsigned frame = 0; frame < 6; frame++) {
        unsigned front = raphael_front, back = raphael_back;
        uint8_t before[16]; memcpy(before, pixels[front], sizeof(before));
        uint8_t *p = raphael_display_back(true);
        assert(p == pixels[back] && !memcmp(p, before, sizeof(before)));
        p[0] = (uint8_t)(frame + 10);
        assert(!memcmp(pixels[front], before, sizeof(before)));
        assert(raphael_display_present());
        assert(raphael_front == back && raphael_back == (back + 1) % 3);
        assert(loader_framebuffer == 0x9c000000ull + back * 0xa00000ull);
        assert(regs[0x5014/4] == loader_framebuffer && regs[0x201c/4] == 0);
    }
    uint8_t old[16]; memcpy(old, pixels[raphael_back], sizeof(old));
    assert(raphael_display_back(false) == pixels[raphael_back]);
    assert(!memcmp(old, pixels[raphael_back], sizeof(old)));
    assert(raphael_display_back(true)); assert(raphael_display_present());
    unsigned front = raphael_front;
    assert(front != 0);
    latch = false;
    assert(raphael_display_back(true));
    assert(!raphael_display_present() && !raphael_flipping);
    assert(regs[0x5014/4] == 0x9c000000 && loader_framebuffer == 0x9c000000);
    assert(!memcmp(pixels[0], pixels[front], sizeof(pixels[0])));
    assert(raphael_display_back(true) == NULL);
    raphael_display_quiesce();
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-display-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
print('PASS: actual scanout rotation, front preserved, TE latch and timeout rollback (ASan/UBSan)')
