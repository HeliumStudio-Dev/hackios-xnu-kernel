#!/usr/bin/env python3
"""Check stopped-MSA diagnostics stay inside the owned range and bound log output."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
function = re.search(r'static void\nicnss_dump_strings\(.*?\n\}', source, re.S)[0]
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
static char *strnstr(const char *text,const char *needle,size_t limit) {
 size_t size=strlen(needle);if(!size)return (char*)text;
 for(size_t at=0;at+size<=limit&&text[at];at++)if(!memcmp(text+at,needle,size))return (char*)text+at;
 return NULL;
}
#define VM_WIMG_WCOMB 1
static uint8_t memory[4096];
static unsigned maps,unmaps,lines;
static char output[32768];static size_t used;
static vm_offset_t ml_io_map_unmappable(uint64_t addr,uint32_t size,unsigned flags) {
 assert(addr==0x8bc00000&&size==sizeof(memory)&&flags==VM_WIMG_WCOMB);maps++;return (uintptr_t)memory;
}
static void ml_io_unmap(vm_offset_t addr,uint32_t size) {assert(addr==(uintptr_t)memory&&size==sizeof(memory));unmaps++;}
static void capture(const char *format,...) {
 va_list ap;va_start(ap,format);int bytes=vsnprintf(output+used,sizeof(output)-used,format,ap);va_end(ap);
 assert(bytes>=0&&(size_t)bytes<sizeof(output)-used);used+=bytes;lines++;
}
#define printf capture
''' + function + r'''
int main(void) {
 icnss_dump_strings(0x8bbff000,4096);icnss_dump_strings(0x8bd80000,4096);
 icnss_dump_strings(UINT64_MAX,4096);icnss_dump_strings(0x8bc00000,0);
 icnss_dump_strings(0x8bc00000,0x181000);icnss_dump_strings(0x8bc00001,4096);icnss_dump_strings(0x8bc00000,4097);
 assert(!maps&&!unmaps);
 memcpy(memory+64,"ASSERT wlan.c line 27",21);memcpy(memory+sizeof(memory)-12,"ERR boundary",12);
 icnss_dump_strings(0x8bc00000,sizeof(memory));assert(maps==1&&unmaps==1);
 assert(strstr(output,"ASSERT wlan.c line 27")&&strstr(output,"ERR boundary"));
 memset(memory,'A',sizeof(memory));used=lines=0;output[0]=0;icnss_dump_strings(0x8bc00000,sizeof(memory));assert(maps==2&&unmaps==2);
 memset(memory,0,sizeof(memory));for(unsigned i=0;i<100;i++)memcpy(memory+32*i,"ASSERT bound.c",15);
 used=lines=0;output[0]=0;icnss_dump_strings(0x8bc00000,sizeof(memory));assert(lines==41&&maps==3&&unmaps==3);
 puts("PASS: MSA range/alignment checks, bounded strings at the final byte, long runs and capped diagnostic output");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-dump-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
