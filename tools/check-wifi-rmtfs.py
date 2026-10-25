#!/usr/bin/env python3
"""Exercise the actual RAM-only RMTFS protocol and every file/DMA boundary."""
from pathlib import Path
import re
import subprocess
import tempfile
s = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
state = s[s.index('#define RMTFS_BYTES'):s.index('#define VM_HLOS')]
f = '\n'.join(re.search(r'static (?:const uint8_t \*|uint32_t|void)\n' + name + r'\(.*?\n\}', s, re.S)[0]
              for name in ('qmi_field', 'qmi_number', 'mpss_storage_request'))
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __unused __attribute__((unused))
typedef uintptr_t vm_offset_t;
struct hakios_qrtr_port { int unused; };
static uint32_t qrtr_peer;
static unsigned sent;
static uint8_t response[32];
static size_t response_size;
static int qrtr_send(struct hakios_qrtr_port *p, uint32_t n, uint32_t port, const void *data, size_t size) {
    assert(p && n == qrtr_peer && port == 8 && size <= sizeof(response));
    memcpy(response, data, size); response_size = size; sent++; return 0;
}
static void settle(void) { }
static void quiet_print(const char *s, ...) { (void)s; }
#define printf quiet_print
''' + state + f + r'''
static uint8_t snapshot[4][4096], original[4][4096], shared[RMTFS_BYTES], request[3200];
static struct hakios_qrtr_port port;
static size_t length;
static void begin(unsigned message) {
    memset(request, 0, sizeof(request)); request[1] = 7; request[3] = message; length = 7;
}
static void tlv(unsigned type, const void *data, size_t size) {
    assert(length + 3 + size <= sizeof(request));
    request[length++] = type; request[length++] = size; request[length++] = size >> 8;
    memcpy(request + length, data, size); length += size;
}
static void number(unsigned type, uint32_t n) { tlv(type, &n, 4); }
static void send_request(bool success) {
    request[5] = length - 7; request[6] = (length - 7) >> 8;
    unsigned before = sent;
    mpss_storage_request(NULL, 0, 8, request, length);
    assert(sent == before + 1 && response_size >= 14 && response[0] == 2 && response[1] == 7);
    assert((response[10] == 0 && response[12] == 0) == success);
    assert(response[5] == response_size - 7);
}
static void iovec(unsigned id, uint32_t sector, uint32_t address, uint32_t count, uint8_t write) {
    begin(3); number(1, id); tlv(2, &write, 1);
    uint8_t vectors[13] = {1}; memcpy(vectors+1, &sector, 4); memcpy(vectors+5, &address, 4); memcpy(vectors+9, &count, 4);
    tlv(3, vectors, sizeof(vectors)); uint8_t force = 0; tlv(4, &force, 1);
}
int main(void) {
    rmtfs.port = &port; rmtfs.physical = 0x80000000; rmtfs.memory = (uintptr_t)shared; rmtfs.granted = true;
    for (unsigned i = 0; i < 4; i++) {
        memset(snapshot[i], i + 0x31, sizeof(snapshot[i])); memcpy(original[i], snapshot[i], sizeof(snapshot[i]));
        rmtfs.files[i].data = snapshot[i]; rmtfs.files[i].size = sizeof(snapshot[i]);
    }
    const char *paths[] = {"/boot/modem_fs1", "/boot/modem_fs2", "/boot/modem_fsg", "/boot/modem_fsc"};
    for (unsigned i = 0; i < 4; i++) {
        begin(1); tlv(1, paths[i], strlen(paths[i])); send_request(true);
        assert(response_size == 21 && qmi_number(response+17) == i + 1);
    }
    begin(1); tlv(1, "/boot/userdata", 14); send_request(false);
    begin(1); tlv(1, paths[0], strlen(paths[0])); tlv(1, paths[0], strlen(paths[0])); send_request(false);
    begin(4); number(1, 1); number(2, RMTFS_BYTES); send_request(true);
    uint64_t address; memcpy(&address, response+17, 8); assert(address == rmtfs.physical && response_size == 25);
    begin(4); number(1, 1); number(2, RMTFS_BYTES+1); send_request(false);
    iovec(1, 1, 0x80000000, 2, 0); send_request(true);
    assert(rmtfs.reads == 2 && !memcmp(shared, snapshot[0]+512, 1024));
    memset(shared, 0x98, 512); iovec(2, 7, 0x80000000, 1, 1); send_request(true);
    assert(rmtfs.writes == 1 && !memcmp(snapshot[1]+7*512, shared, 512));
    assert(original[1][7*512] == 0x32);
    iovec(1, 8, 0x80000000, 1, 0); send_request(false);
    iovec(1, UINT32_MAX, 0x80000000, UINT32_MAX, 1); send_request(false);
    iovec(1, 0, 0x7fffffff, 1, 1); send_request(false);
    iovec(1, 0, 0x80300000, 1, 1); send_request(false);
    iovec(1, 0, 0x80000000, 1, 2); send_request(false);
    iovec(5, 0, 0x80000000, 1, 0); send_request(false);
    iovec(1, 0, 0x80000000, 1, 0); request[length-1]=2; send_request(false);
    iovec(1, 0, 0x80000000, 1, 0); rmtfs.granted=false; send_request(false); rmtfs.granted=true;
    /* Validate every vector before changing even the first destination. */
    begin(3); number(1,1); uint8_t write=1; tlv(2,&write,1);
    uint32_t v[] = {0,0x80000000,1,8,0x80000000,1}; uint8_t vectors[25]={2}; memcpy(vectors+1,v,sizeof(v));
    tlv(3,vectors,sizeof(vectors)); write=0; tlv(4,&write,1); send_request(false);
    assert(!memcmp(snapshot[0],original[0],4096));
    begin(5); number(1,1); send_request(true); assert(response_size==18 && response[17]==0);
    begin(2); number(1,1); send_request(true); iovec(1,0,0x80000000,1,0); send_request(false);
    begin(4); number(1,2); number(2,1); unsigned before=sent;
    mpss_storage_request(NULL,1,8,request,length); assert(sent==before);
    for (size_t n=0;n<7;n++) { mpss_storage_request(NULL,0,8,request,n); assert(sent==before); }
    request[5]=0; mpss_storage_request(NULL,0,8,request,length); assert(sent==before);
    begin(2); request[7]=1; length=8; send_request(false);
    puts("PASS: RAM-only RMTFS open/close/alloc/status/read/write, malformed TLVs, file and DMA bounds, atomic vector validation");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-rmtfs-') as tmp:
    p = Path(tmp); (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined', str(p/'check.c'), '-o',str(p/'check')],check=True)
    subprocess.run([str(p/'check')],check=True)
