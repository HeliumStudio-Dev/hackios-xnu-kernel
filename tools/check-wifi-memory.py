#!/usr/bin/env python3
"""Check the actual SCM seven-argument ownership descriptor for RMTFS RAM."""
from pathlib import Path
import re
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f=s[s.index('#define VM_HLOS'):s.index('static void\nmpss_storage_stop')]
f=f.replace('__asm__ volatile ("dc civac, %0" : : "r" (at))','(void)at')
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
#define PAGE_SIZE 16384
#define KMA_KOBJECT 1
#define KMA_ZERO 2
#define KMA_DATA 4
#define VM_KERN_MEMORY_IOKIT 0
#define KERN_SUCCESS 0
#define SCM_CALL(s,c) ((s)<<8|(c))
#define RMTFS_BYTES 0x300000u
static int kernel_map;
static uint8_t page[PAGE_SIZE] __attribute__((aligned(PAGE_SIZE)));
static bool fail_alloc, fail_call, grant;
static unsigned allocations, calls;
static struct { uintptr_t permission_page; uint64_t physical; } rmtfs;
static int kmem_alloc(int map, uintptr_t *at, size_t size, unsigned flags, int tag) {
    assert(!map && size==PAGE_SIZE && flags==7 && tag==0); allocations++;
    if(fail_alloc) return 1; *at=(uintptr_t)page; memset(page,0,sizeof(page));return 0;
}
static uint64_t kvtophys(uintptr_t at) { assert(at==(uintptr_t)page);return 0x100000000ull; }
static void settle(void) { }
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
static uint32_t expected_source, expected_dest, expected_perm=6, expected_size=RMTFS_BYTES;
static uint64_t expected_address;
static int32_t scm(const char *why,uint64_t fn,uint64_t arginfo,uint64_t first,uint64_t second,uint64_t third,uint64_t more,uint64_t *answer) {
    assert(why && fn==0xc16 && arginfo==0x1117 && first==0x100000000ull && second==16 && third==first+64 && more==first+256);
    uint64_t *region=(void*)page,*extra=(void*)(page+256);
    uint32_t *src=(void*)(page+64),*dest=(void*)(page+128);unsigned ns=0,nd=0;
    assert(region[0]==expected_address && region[1]==expected_size);
    for(unsigned vmid=0;vmid<32;vmid++) {
        if(expected_source&(1u<<vmid)) assert(src[ns++]==vmid);
        if(expected_dest&(1u<<vmid)) {
            assert(dest[6*nd]==vmid && dest[6*nd+1]==expected_perm);
            for(unsigned j=2;j<6;j++) assert(dest[6*nd+j]==0);
            nd++;
        }
    }
    assert(extra[0]==4*ns && extra[1]==first+128 && extra[2]==24*nd && extra[3]==0);
    calls++;*answer=fail_call?1:0;return 0;
}
'''+f+r'''
int main(void) {
    assert(!mpss_storage_permission(true) && !allocations && !calls);
    rmtfs.physical=0xfc004000; expected_address=rmtfs.physical;
    expected_source=VM_HLOS;expected_dest=VM_HLOS|VM_MSS;
    fail_alloc=true; assert(!mpss_storage_permission(true) && allocations==1 && !calls);
    fail_alloc=false;assert(mpss_storage_permission(true) && allocations==2 && calls==1);
    expected_source=VM_HLOS|VM_MSS;expected_dest=VM_HLOS;
    assert(mpss_storage_permission(false) && allocations==2 && calls==2);
    fail_call=true;assert(!mpss_storage_permission(false) && allocations==2 && calls==3);fail_call=false;
    expected_address=0x8bc00000;expected_size=0x4000;expected_source=VM_HLOS;expected_dest=VM_MSS|VM_WLAN;
    assert(scm_memory_permission(expected_address,expected_size,expected_source,expected_dest,6));
    expected_address=0x8bc04000;expected_size=0x17c000;expected_dest|=VM_CE;
    assert(scm_memory_permission(expected_address,expected_size,expected_source,expected_dest,6));
    expected_source=expected_dest;expected_dest=VM_HLOS;expected_perm=7;
    assert(scm_memory_permission(expected_address,expected_size,expected_source,expected_dest,7));
    unsigned before=calls;
    assert(!scm_memory_permission(0,4096,VM_HLOS,VM_MSS,6));
    assert(!scm_memory_permission(1,4096,VM_HLOS,VM_MSS,6));
    assert(!scm_memory_permission(4096,1,VM_HLOS,VM_MSS,6));
    assert(!scm_memory_permission(UINT64_MAX-4095,8192,VM_HLOS,VM_MSS,6));
    assert(!scm_memory_permission(4096,4096,0,VM_MSS,6));
    assert(!scm_memory_permission(4096,4096,VM_HLOS,1,6));
    assert(!scm_memory_permission(4096,4096,VM_HLOS,VM_MSS,0));
    assert(!scm_memory_permission(4096,4096,VM_HLOS,VM_HLOS|VM_MSS|VM_WLAN|VM_CE,6));
    assert(calls==before);
    puts("PASS: RMTFS and secure/nonsecure MSA ownership, extended arguments, bounds, failures and metadata reuse");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-memory-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
