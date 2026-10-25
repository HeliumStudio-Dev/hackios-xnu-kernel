#!/usr/bin/env python3
"""Host checks for the actual GT9886 report decoder: check-raphael-touch.py."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/raphael_touch.c').read_text()
start = source.index('static int\ntouch_normandy_decode(')
end = source.index('\nstatic int\n', start + 1)
decoder = source[start:end]
start = source.index('static bool\ntouch_clocks(')
end = source.index('\nstatic ', start + 1)
clocks = source[start:end]
start = source.index('static void\ntouch_report(')
end = source.index('\nstatic ', start + 1)
report = source[start:end]
start = source.index('static bool\ntouch_idle_fifo(')
end = source.index('\nvoid\n', start + 1)
fifo = source[start:end]
waits = '\n'.join(re.search(r'static void\n' + name + r'\(.*?\n\}', source, re.S)[0]
                  for name in ('touch_wait_until', 'touch_wait'))
harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#define TOUCH_MAX 10u
#define NSEC_PER_MSEC 1000000ull
#define THREAD_UNINT 0
#define THREAD_CONTINUE_NULL 0
static int touch_sleep_chan;
static uint64_t now, scheduled;
static unsigned blocked;
static void clock_interval_to_deadline(unsigned n, uint64_t scale, uint64_t *at) { *at = now + n * scale; }
static int assert_wait_deadline(void *chan, int kind, uint64_t at) {
    assert(chan == &touch_sleep_chan && kind == THREAD_UNINT); scheduled = at; return 0;
}
static void thread_block(int continuation) {
    assert(continuation == THREAD_CONTINUE_NULL); if (now < scheduled) now = scheduled; blocked++;
}
''' + waits + decoder + r'''
typedef uintptr_t vm_offset_t;
#define HAKIOS_TOUCH_DOWN 1
#define HAKIOS_TOUCH_MOVE 2
#define HAKIOS_TOUCH_UP 3
static struct { vm_offset_t gcc, se; uint32_t active; int x[10], y[10]; } st;
static unsigned events, type, contact, nx, ny;
static void hakios_touch_post(unsigned t, unsigned id, unsigned x, unsigned y) {
    events++; type = t; contact = id; nx = x; ny = y;
}
#define SE_STATUS 0x040u
#define SE_RX 0x780u
#define SE_TX_COUNT 0x800u
#define SE_RX_COUNT 0x804u
#define SE_IRQ_CLR 0x618u
static uint32_t regs[0x60000 / 4];
static unsigned drained;
static bool stuck;
static uint32_t touch_rd(vm_offset_t base, uint32_t off) { (void)base; if (off == SE_RX) { drained++; if (!stuck) regs[SE_RX_COUNT / 4]--; }
    return regs[off / 4]; }
static void touch_wr(vm_offset_t base, uint32_t off, uint32_t value) { (void)base; regs[off / 4] = value; }
static bool touch_wait_clear(vm_offset_t base, uint32_t off, uint32_t mask) { return !(touch_rd(base, off) & mask); }
''' + report + clocks + fifo + r'''
static void checksum(uint8_t *b, unsigned n) {
    unsigned sum = 0;
    for (unsigned i = 0; i < n - 1; i++) sum += b[i];
    b[n - 1] = (uint8_t)-sum;
}
static void point(uint8_t *b, unsigned i, unsigned id, unsigned x, unsigned y) {
    uint8_t *p = b + 2 + 8 * i;
    p[0] = id; p[1] = x; p[2] = x >> 8; p[3] = y; p[4] = y >> 8;
}
int main(void) {
    uint64_t deadline;
    clock_interval_to_deadline(8, NSEC_PER_MSEC, &deadline);
    now = 3000000; touch_wait_until(deadline); assert(now == 8000000 && blocked == 1);
    now = 12000000; touch_wait_until(deadline); assert(now == 12000000 && blocked == 2);
    touch_wait(2); assert(now == 14000000 && blocked == 3);
    regs[SE_RX_COUNT / 4] = 3;
    assert(touch_idle_fifo() && drained == 3 && regs[SE_RX_COUNT / 4] == 0);
    regs[SE_STATUS / 4] = 1; regs[SE_RX_COUNT / 4] = 2;
    assert(!touch_idle_fifo() && drained == 3 && regs[SE_RX_COUNT / 4] == 2);
    regs[SE_STATUS / 4] = 0; regs[SE_TX_COUNT / 4] = 1;
    assert(!touch_idle_fifo() && drained == 5);
    regs[SE_TX_COUNT / 4] = 0; regs[SE_RX_COUNT / 4] = 1; stuck = true;
    assert(!touch_idle_fifo() && drained == 69);
    stuck = false; regs[SE_RX_COUNT / 4] = 0;
    regs[(0x1e3a8 + 0x14) / 4] = 1;
    regs[(0x1e3a8 + 0x1c) / 4] = 1;
    regs[0x1e008 / 4] = 0x80000002u; /* observed idle HWCG state */
    assert(touch_clocks() && regs[0x52014 / 4] == 0x46);
    regs[0x1e008 / 4] = 0x80000000u; /* genuinely halted, no HWCG */
    assert(!touch_clocks());
    regs[0x1e008 / 4] = 0x80000002u;
    regs[0x1e3a4 / 4] = 0x80000000u; /* serial clock must still be checked */
    assert(!touch_clocks());
    regs[(0x1e3a8 + 0x1c) / 4] = 0x601; /* unexpected parent: refuse */
    assert(!touch_clocks());
    uint8_t b[84] = {0x80, 0};
    int x[10] = {0}, y[10] = {0}; uint32_t mask = 0x3ff;
    checksum(b, 4);
    assert(!touch_normandy_decode(b, 4, false, &mask, x, y) && mask == 0);
    b[1] = 1; point(b, 0, 9, 1079, 2339); checksum(b, 12);
    assert(!touch_normandy_decode(b, 12, false, &mask, x, y));
    assert(mask == (1u << 9) && x[9] == 1079 && y[9] == 2339);
    assert(!touch_normandy_decode(b, 12, true, &mask, x, y));
    assert(x[9] == 0 && y[9] == 0);
    for (unsigned len = 0; len < 12; len++)
        assert(touch_normandy_decode(b, len, false, &mask, x, y));
    b[11] ^= 1;
    assert(touch_normandy_decode(b, 12, false, &mask, x, y) == EIO);
    checksum(b, 12); b[0] = 0;
    assert(touch_normandy_decode(b, 12, false, &mask, x, y)); b[0] = 0x80;
    point(b, 0, 10, 0, 0); checksum(b, 12);
    assert(touch_normandy_decode(b, 12, false, &mask, x, y));
    point(b, 0, 0x80, 0, 0); checksum(b, 12);
    assert(touch_normandy_decode(b, 12, false, &mask, x, y));
    point(b, 0, 0, 1080, 0); checksum(b, 12);
    assert(touch_normandy_decode(b, 12, false, &mask, x, y));
    point(b, 0, 0, 0, 2340); checksum(b, 12);
    assert(touch_normandy_decode(b, 12, false, &mask, x, y));
    b[1] = 2; point(b, 0, 0, 0, 0); point(b, 1, 0, 10, 20); checksum(b, 20);
    assert(touch_normandy_decode(b, 20, false, &mask, x, y));
    b[1] = 10;
    for (unsigned i = 0; i < 10; i++) point(b, i, i, 100 + i, 200 + i);
    checksum(b, 84);
    assert(!touch_normandy_decode(b, 84, false, &mask, x, y) && mask == 0x3ff);
    assert(x[0] == 100 && y[9] == 209);
    x[0] = 0; y[0] = 0; touch_report(1, x, y);
    assert(events == 1 && type == HAKIOS_TOUCH_DOWN && contact == 0 && nx == 0 && ny == 0);
    touch_report(1, x, y); assert(events == 1);
    x[0] = 1079; y[0] = 2339; touch_report(1, x, y);
    assert(events == 2 && type == HAKIOS_TOUCH_MOVE && nx == 65535 && ny == 65535);
    touch_report(0, x, y);
    assert(events == 3 && type == HAKIOS_TOUCH_UP && nx == 65535 && ny == 65535 && st.active == 0);
    b[1] = 11; checksum(b, 84);
    assert(touch_normandy_decode(b, 84, false, &mask, x, y));
}
'''
with tempfile.TemporaryDirectory(prefix='raphael-touch-') as tmp:
    c, exe = Path(tmp) / 'check.c', Path(tmp) / 'check'
    c.write_text(harness)
    subprocess.run([os.environ.get('CC', 'cc'), '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-g', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print('PASS: actual Normandy decoder, idle FIFO cleanup and clock guards, including idle HWCG, stopped clocks and invalid DFS parent (ASan/UBSan)')
