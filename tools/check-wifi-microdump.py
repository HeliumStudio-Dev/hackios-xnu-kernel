#!/usr/bin/env python3
"""Check MPSS microdump reads remain inside the native SMEM item."""
from pathlib import Path
import re
import subprocess
import tempfile
source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
function = re.search(r'static void\nmpss_microdump\(.*?\n\}', source, re.S)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t item_size,base=0x1000,read_bytes;
static bool fail_read;
static uint32_t smem_item(unsigned item,uint32_t *size) {assert(item==611);*size=item_size;return base;}
static bool smem_peek(uint32_t at,void *data,uint32_t bytes) {
 assert(at==base+read_bytes&&bytes<=16&&read_bytes+bytes<=item_size);
 if(fail_read)return false;memset(data,0x41,bytes);read_bytes+=bytes;return true;
}
static void capture(const char *fmt,...) {(void)fmt;}
#define printf capture
''' + function + r'''
int main(void) {
 mpss_microdump("empty");assert(!read_bytes);
 item_size=4097;mpss_microdump("invalid");assert(!read_bytes);
 item_size=4096;mpss_microdump("before");assert(read_bytes==4096);
 item_size=19;read_bytes=0;mpss_microdump("after");assert(read_bytes==19);
 read_bytes=0;fail_read=true;mpss_microdump("failed");assert(!read_bytes);
 fail_read=false;base=0;mpss_microdump("missing");assert(!read_bytes);
 puts("PASS: native SMEM microdump item, bounded reads, short final row, missing item and failed reads");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-microdump-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
