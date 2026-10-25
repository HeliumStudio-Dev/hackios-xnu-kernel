#!/usr/bin/env python3
"""Check the actual MPSS proxy table selection and RPMh handshake without MMIO."""
from pathlib import Path
import re
import subprocess
import tempfile
s = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
decls = s[s.index('struct cmd_db_slave {'):s.index('static const struct cmd_db_header *cmd_db;')]
f = '\n'.join(re.search(r'static bool\n'+n+r'\(.*?\n\}', s, re.S)[0] for n in ('wifi_rpmh_write','mpss_proxy')) + '\n' + s[s.index('static bool icnss_rails_touched;'):s.index('static struct { uint64_t address; uint32_t size, owners; } icnss_regions')]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#define __offsetof offsetof
#define CMD_DB_SIZE 131072u
#define RSC_TCS(n) (0xd00 + 672 * (n))
#define TCS_STATUS 0x18
#define TCS_CONTROL 0x14
#define TCS_ENABLED 0x1c
#define TCS_COMMAND(i) (0x30 + 20 * (i))
typedef uintptr_t vm_offset_t;
''' + decls + r'''
static union { uint64_t align; uint8_t data[CMD_DB_SIZE]; } blob;
static const struct cmd_db_header *cmd_db = (const void *)blob.data;
static struct { uintptr_t base; } rsc;
static uint32_t regs[16384], writes, waits;
static int missing;
static bool complete, clock_complete;
static unsigned clock_on, clock_off;
static uint32_t rd(uintptr_t at) { assert(at < sizeof(regs)); return regs[at / 4]; }
static void wr(uintptr_t at, uint32_t v) {
    assert(at < sizeof(regs)); writes++; regs[at / 4] = v;
    if (at == RSC_TCS(0) + 8) regs[(RSC_TCS(0) + 4) / 4] &= ~v;
    if (at == RSC_TCS(1) + TCS_CONTROL && (v & (1u << 24)) && complete)
        regs[(RSC_TCS(0) + 4) / 4] |= 2;
}
static void need(void *p) { assert(p == &rsc); }
static void settle(void) { }
static void sleep_us(unsigned n) { assert(n == 100); waits++; }
static void quiet_print(const char *s, ...) { (void)s; }
#define printf quiet_print
static bool mailbox_send(const char *text) {
    if (!strcmp(text,"{class: clock, res: qdss, val: 1}")) {
        assert(complete && !regs[(RSC_TCS(1)+TCS_ENABLED)/4]);
        clock_on++;
    } else {
        assert(!strcmp(text,"{class: clock, res: qdss, val: 0}"));
        clock_off++;
    }
    return clock_complete;
}
static const struct cmd_db_entry *rpmh_resource(const char *name, uint32_t at) {
    const struct cmd_db_entry *entries = (const void *)(cmd_db->data + 64);
    const char *names[] = {"cx.lvl", "mss.lvl", "xo.lvl", "ldoa1", "ldoa7", "ldoc2", "ldoc10", "ldoc11"};
    assert(!at);
    for (unsigned i = 0; i < 8; i++) if (!strcmp(name, names[i])) return missing == (int)i ? NULL : &entries[i];
    assert(0); return NULL;
}
''' + f + r'''
static struct cmd_db_entry *entry(unsigned i) { return (void *)(blob.data + offsetof(struct cmd_db_header, data) + 64 + i * sizeof(struct cmd_db_entry)); }
static void reset(void) {
    memset(&blob, 0, sizeof(blob)); memset(regs, 0, sizeof(regs));
    struct cmd_db_header *db = (void *)blob.data;
    db->slave[0] = (struct cmd_db_slave){.id=3, .header_offset=64, .data_offset=1024, .count=8};
    for (unsigned i = 0; i < 8; i++) {
        *entry(i) = (struct cmd_db_entry){.address=i<3 ? 0x30000 + 4*i : 0x40000 + 0x100*(i-3), .length=8, .offset=16 * i};
        uint16_t levels[] = {0, 64, 256, 384};
        memcpy((void *)(db->data + 1024 + 16 * i), levels, sizeof(levels));
    }
    missing = -1; writes = waits = clock_on = clock_off = 0; complete = clock_complete = true;
    regs[(RSC_TCS(1) + TCS_STATUS) / 4] = 1;
    regs[RSC_TCS(0) / 4] = 0x100;
}
int main(void) {
    reset(); assert(mpss_proxy());
    for (unsigned i = 0; i < 3; i++) {
        assert(regs[(RSC_TCS(1) + TCS_COMMAND(i) + 4) / 4] == 0x30000 + 4 * i);
        assert(regs[(RSC_TCS(1) + TCS_COMMAND(i) + 8) / 4] == 3);
    }
    assert(regs[RSC_TCS(0) / 4] == 0x100 && !regs[(RSC_TCS(1) + TCS_ENABLED) / 4]);
    assert(!regs[(RSC_TCS(1) + TCS_CONTROL) / 4] && !waits);
    reset(); complete = false; assert(!mpss_proxy() && waits == 2000);
    assert(regs[RSC_TCS(0) / 4] == 0x100 && !regs[(RSC_TCS(1) + TCS_ENABLED) / 4]);
    for (unsigned i = 0; i < 3; i++) { reset(); missing = i; assert(!mpss_proxy() && !writes); }
    reset(); regs[(RSC_TCS(1) + TCS_STATUS) / 4] = 0; assert(!mpss_proxy() && !writes);
    reset(); entry(0)->length = 6; assert(!mpss_proxy() && !writes);
    reset(); entry(1)->address = 0x40000; assert(!mpss_proxy() && !writes);
    reset(); struct cmd_db_header *db = (void *)blob.data;
    db->slave[0].data_offset = 65535; entry(0)->offset = 65535;
    assert(!mpss_proxy() && !writes);
    reset(); assert(icnss_power(true) && icnss_rails_touched && icnss_qdss_touched && clock_on==1);
    const uint32_t voltage[]={752,1800,1304,3312,3104};
    for(unsigned i=0;i<5;i++) {
        unsigned command=3*i;
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command)+4)/4]==0x40000+0x100*i);
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command)+8)/4]==voltage[i]);
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command+1)+4)/4]==0x40008+0x100*i);
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command+1)+8)/4]==(i==3?7u:4u));
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command+2)+4)/4]==0x40004+0x100*i);
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(command+2)+8)/4]==1);
    }
    assert(icnss_power(false) && !icnss_rails_touched && !icnss_qdss_touched && clock_off==1);
    for(unsigned i=0;i<5;i++) {
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(i)+4)/4]==0x40004+0x100*(4-i));
        assert(regs[(RSC_TCS(1)+TCS_COMMAND(i)+8)/4]==0);
    }
    for (unsigned i=3;i<8;i++) {reset(); missing=i;assert(!icnss_power(true)&&!writes&&!icnss_rails_touched&&!icnss_qdss_touched&&!clock_on);}
    reset(); complete=false;assert(!icnss_power(true)&&icnss_rails_touched);
    complete=true;assert(icnss_power(false)&&!icnss_rails_touched);
    reset(); clock_complete=false;
    assert(!icnss_power(true)&&icnss_rails_touched&&icnss_qdss_touched&&clock_on==1);
    assert(!icnss_power(false)&&!icnss_rails_touched&&icnss_qdss_touched&&clock_off==1);
    clock_complete=true;assert(icnss_power(false)&&!icnss_qdss_touched&&clock_off==2);
    unsigned before=writes;assert(!wifi_rpmh_write(NULL,NULL,0)&&!wifi_rpmh_write(NULL,NULL,17)&&writes==before);
    puts("PASS: MPSS proxy, five WLAN rails, QDSS on/off, missing resources, busy TCS, timeout and failed-vote cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-proxy-') as tmp:
    p = Path(tmp)
    (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined', str(p / 'check.c'), '-o', str(p / 'check')], check=True)
    subprocess.run([str(p / 'check')], check=True)
