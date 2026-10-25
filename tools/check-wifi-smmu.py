#!/usr/bin/env python3
"""Exercise native WLAN stream ownership and the MSA identity page tables."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
# Keep the register definitions independent of the diagnostic printing routine.
plain = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
constants = '\n'.join(line for line in plain.splitlines() if line.startswith('#define SMMU_') or line.startswith('#define RADIO_STREAM'))
tables = source[source.index('#define RADIO_ADDRESSES '):source.index('/* Which match register and which context are free;')]
tables = tables.replace('__asm__ volatile ("dc civac, %0" : : "r" (line));', '(void)line;')
find = re.search(r'static bool\nradio_space_find\(.*?\n\}', source, re.S)[0]
prepare = re.search(r'static bool\nicnss_smmu_prepare\(.*?\n\}', source, re.S)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uintptr_t vm_offset_t;
struct block {const char *name; uint32_t phys; uintptr_t base;};
static uint32_t registers[0x100000/4];
static struct block apps_smmu={"apps",0x15000000,(uintptr_t)registers};
static unsigned step, locks;
static int hakios_smmu_lock, kernel_map;
static bool fail_alloc;
#define KMA_KOBJECT 0
#define KMA_ZERO 0
#define KMA_DATA 0
#define VM_KERN_MEMORY_IOKIT 0
#define KERN_SUCCESS 0
#define round_page(n) (n)
static bool hakios_is_raphael(void) {return true;}
static uint64_t kvtophys(vm_offset_t value) {return value;}
static void settle(void) {}
static void lck_mtx_lock(int *p) {assert(p==&hakios_smmu_lock&&!locks);locks++;}
static void lck_mtx_unlock(int *p) {assert(p==&hakios_smmu_lock&&locks==1);locks--;}
static int kmem_alloc(int map,vm_offset_t *p,size_t size,int flags,int tag) {
 (void)map;(void)flags;(void)tag;if(fail_alloc)return 1;
 void *memory=aligned_alloc(4096,size);assert(memory);memset(memory,0,size);*p=(uintptr_t)memory;return 0;
}
static uint32_t rd(uintptr_t address) {return *(uint32_t*)address;}
static uint32_t get(struct block *b,const char *name,uint32_t offset) {
 (void)name;if(!b->base)b->base=(uintptr_t)registers+b->phys-apps_smmu.phys;return rd(b->base+offset);
}
static void quiet(const char *format,...) {(void)format;}
#define printf quiet
''' + constants + '\n' + tables + '\n' + find + r'''
static bool radio_space_on(void) {assert(locks==1&&radio_space.found);radio_space.on=true;return true;}
''' + prepare + r'''
static void reset(void) {
 free((void*)radio_space.tables);memset(&radio_space,0,sizeof(radio_space));memset(registers,0,sizeof(registers));
 apps_smmu_second.base=apps_smmu_context.base=0;fail_alloc=false;assert(!locks);
 registers[SMMU_SCR0/4]=0x2f0406;registers[SMMU_IDR0/4]=0x4c017e5e;registers[SMMU_IDR1/4]=0x60000038;
}
static uint64_t leaf(uint64_t address) {
 uint64_t value=radio_table(0)[address>>30&511];if(!(value&1))return 0;
 uint64_t *level2=(void*)(uintptr_t)(value&PTE_ADDRESS);value=level2[address>>21&511];if(!(value&1))return 0;
 return ((uint64_t*)(uintptr_t)(value&PTE_ADDRESS))[address>>12&511];
}
int main(void) {
 reset();assert(RADIO_STREAM==0x640&&icnss_smmu_prepare()&&!locks);
 assert(radio_space.match==0&&radio_space.context==0&&radio_space.table_count==3);
 for(uint64_t at=0x8bc00000;at<0x8bd80000;at+=4096)assert(leaf(at)==(at|RADIO_PTE));
 assert(!leaf(0x8bbff000)&&!leaf(0x8bd80000)&&!leaf(0xa0000000));
 vm_offset_t old=radio_space.tables;assert(icnss_smmu_prepare()&&radio_space.tables==old);
 reset();registers[SMMU_SMR(0)/4]=0x80010640;assert(!icnss_smmu_prepare()&&!radio_space.tables&&!locks);
 reset();registers[SMMU_SMR(0)/4]=0x87ff0000;assert(!icnss_smmu_prepare()&&!locks);
 reset();registers[SMMU_SMR(0)/4]=0x80010020;registers[SMMU_S2CR(0)/4]=0;
 assert(icnss_smmu_prepare()&&radio_space.match==1&&radio_space.context==1);
 reset();registers[SMMU_IDR1/4]=0;assert(!icnss_smmu_prepare()&&!locks);
 reset();fail_alloc=true;assert(!icnss_smmu_prepare()&&!radio_space.on&&!locks);
 reset();puts("PASS: native stream ownership, bounded MSA identity mapping, context selection, allocation failure and lock balance");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-smmu-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-Wno-format',
                    '-fsanitize=address,undefined', str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
