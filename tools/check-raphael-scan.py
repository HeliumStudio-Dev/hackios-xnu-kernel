#!/usr/bin/env python3
"""Run the actual scan backend with simulated TE phase, clock loss and stalled counters."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnu/files/bsd/dev/hakios.display.c').read_text()
source = re.sub(r'^#include .*\n', '', source, flags=re.M)
header = (root / 'xnu/files/bsd/sys/hakios.display.h').read_text()
shape = re.search(r'struct hakios_display_scan \{.*?\n\};', header, re.S)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
typedef uintptr_t vm_size_t;
#define NSEC_PER_MSEC 1000000ull
#define NSEC_PER_USEC 1000ull
static int scan_printf(const char *format, ...) { (void)format; return 0; }
#define printf scan_printf
#define hakios_board_addr(name, fallback) (fallback)
static uint64_t now, period = 16660000, tick_ns = 7000;
static bool alive = true, stalled, raphael = true;
static unsigned option = 1, counter_reads;
static uint64_t mach_absolute_time(void) { return now; }
static void absolutetime_to_nanoseconds(uint64_t time, uint64_t *out) { *out = time; }
static void delay_for_interval(uint32_t n, uint64_t scale) { now += n * scale; }
static bool PE_parse_boot_argn(const char *name, void *out, unsigned size) {
 assert(!strcmp(name,"fb_scan") && size == 4); *(uint32_t *)out = option; return true;
}
static int hakios_is_raphael(void) { return raphael; }
vm_offset_t ml_io_map(vm_offset_t address, vm_size_t size) {
 (void)address; (void)size; assert(!"raphael must not map redwood clocks or INTF"); return 0;
}
int raphael_display_scan_counter(uint32_t *line) {
 counter_reads++;
 if (!alive) return 0;
 *line = stalled ? 0 : (uint32_t)((now % period) / tick_ns); return 1;
}
''' + shape + source + r'''
int main(void) {
 option=0; assert(!hakios_display_scan_start() && !counter_reads);
 option=1;
 for (unsigned rate=0; rate<3; rate++) {
  scan.ok=0; now=1230000;
  period=rate==0?16660000:rate==1?33320000:8330000;
  tick_ns=rate==2?3500:7000;
  assert(hakios_display_scan_start() && hakios_display_scan());
  assert(scan.frame_ns > period-100000 && scan.frame_ns < period+100000);
  assert(scan.line_ns > tick_ns-100 && scan.line_ns < tick_ns+100);
  assert(scan.lines >= 2340 && scan.millihz >= 29900 && scan.millihz <= 121000);
  now = period*5 + period/2;
  uint32_t frame=99, line=hakios_display_line(&frame);
  assert(frame==0 && line>scan.lines/3 && line<scan.lines*2/3);
  uint64_t next=hakios_display_next_frame_ns();
  assert(next>period/3 && next<period*2/3);
 }
 alive=false; assert(hakios_display_next_frame_ns()==0 && !hakios_display_scan());
 assert(!hakios_display_scan_start()); alive=true;
 scan.ok=0; stalled=true; now=0;
 assert(!hakios_display_scan_start() && now<=151*NSEC_PER_MSEC && !hakios_display_scan());
 stalled=false; tick_ns=1000; period=2000000; now=0;
 assert(!hakios_display_scan_start() && !hakios_display_scan()); /* Reject implausible frame timing. */
 puts("PASS: actual command TE calibration, 30/60/120 Hz, phase, bounded fallback");
}
'''
with tempfile.TemporaryDirectory(prefix='raphael-scan-') as tmp:
    p = Path(tmp)
    (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(p / 'check.c'), '-o', str(p / 'check')], check=True)
    subprocess.run([str(p / 'check')], check=True)
