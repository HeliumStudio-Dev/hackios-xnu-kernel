#!/usr/bin/env python3
"""Check the actual bounded QRTR firmware TFTP implementation."""
from pathlib import Path
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f=s[s.index('/* Firmware transfer over QRTR,'):s.index('/* Native diagfwd_socket:')]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __unused __attribute__((unused))
#define Z_WAITOK 0
#define QRTR_NEW_SERVER 4
#define QRTR_CONTROL UINT32_MAX
#define QRTR_US 1
struct hakios_qrtr_port { unsigned used; void *context; } ports[16];
struct qrtr_control { uint32_t command,words[4]; };
static uint32_t qrtr_peer;
static uint8_t firmware[4*1024*1024],output[32][8192];
static size_t output_size[32],firmware_size=32;
static unsigned packets,closes;
static bool missing,fail_send;
static void *kalloc_data(size_t size,int flags) { (void)flags; return malloc(size); }
static void kfree_data(void *p,size_t size) { (void)size;free(p); }
static const uint8_t *image_file(const char *name,uint64_t *size) { assert(!strcmp(name,"wlanmdsp.mbn"));*size=firmware_size;return missing?NULL:firmware; }
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
static struct hakios_qrtr_port *qrtr_open(void (*cb)(void*,uint32_t,uint32_t,const void*,size_t),void *server,void *context) {
    assert(cb&&!server);for(unsigned i=0;i<16;i++)if(!ports[i].used){ports[i].used=1;ports[i].context=context;return &ports[i];}return NULL;
}
static void qrtr_close(struct hakios_qrtr_port *p) { assert(p&&p->used);p->used=0;closes++; }
static int qrtr_send(struct hakios_qrtr_port *p,uint32_t node,uint32_t port,const void *data,size_t size) {
    assert(p&&p->used&&node==0&&port==120&&packets<32&&size<=8192);
    if(fail_send)return -1;memcpy(output[packets],data,size);output_size[packets++]=size;return 0;
}
static int qrtr_out_packet(unsigned type,unsigned from,unsigned to,unsigned port,const void *data,size_t size) {
    assert(type==4&&from==UINT32_MAX&&to==0&&port==UINT32_MAX&&data&&size==sizeof(struct qrtr_control));return 0;
}
'''+f+r'''
static uint8_t request[2300];static size_t length;
static void text(const char *s) { size_t n=strlen(s)+1;assert(length+n<=sizeof(request));memcpy(request+length,s,n);length+=n; }
static void rrq(const char *path) { memset(request,0,sizeof(request));request[1]=1;length=2;text(path);text("octet"); }
static void option(const char *n,const char *v) { text(n);text(v); }
static void request_send(void) { tftp_request(NULL,0,120,request,length); }
static struct tftp_reader *reader(void) { for(unsigned i=0;i<4;i++)if(tftp_readers[i].port)return &tftp_readers[i];assert(0);return NULL; }
static void ack(unsigned block) { uint8_t a[]={0,4,block>>8,block};tftp_data(reader(),0,120,a,4); }
static void reset_output(void) { packets=0; }
static void error(unsigned e) { assert(packets&&output[packets-1][1]==5&&output[packets-1][3]==e);reset_output(); }
static void end(void) { uint8_t e[]={0,5,0,9};tftp_data(reader(),0,120,e,4); }
int main(void) {
    for(unsigned i=0;i<sizeof(firmware);i++)firmware[i]=(uint8_t)i;
    assert(tftp_start());
    const char *path="/readonly/firmware/image/wlanmdsp.mbn";
    rrq(path);request_send();assert(packets==1&&output_size[0]==36&&output[0][1]==3&&!memcmp(output[0]+4,firmware,32));
    ack(1);assert(closes==1);reset_output();
    rrq(path);option("blksize","8");option("wsize","2");option("tsize","0");request_send();
    assert(packets==1&&output[0][1]==6);reset_output();ack(0);
    assert(packets==2&&output_size[0]==12&&output[0][3]==1&&output[1][3]==2);reset_output();ack(2);
    assert(packets==2&&output[0][3]==3&&output[1][3]==4);reset_output();ack(4);
    assert(packets==1&&output_size[0]==4&&output[0][3]==5);ack(5);reset_output();
    rrq(path);option("rsize","5");option("seek","3");request_send();reset_output();ack(0);
    assert(packets==1&&output_size[0]==9&&!memcmp(output[0]+4,firmware+3,5));ack(1);reset_output();
    rrq(path);option("blksize","65464");option("wsize","65535");request_send();
    assert(reader()->block_size==7680&&reader()->window==10);end();reset_output();
    rrq("/readonly/firmware/image/nv-modemst1");request_send();error(1);
    rrq("/readonly/firmware/image/../wlanmdsp.mbn");request_send();error(1);
    rrq(path);request[1]=2;request_send();error(2);
    rrq(path);option("blksize","7");request_send();error(8);
    rrq(path);option("seek","33");request_send();error(8);
    rrq(path);option("seek","31");option("rsize","2");request_send();error(8);
    rrq(path);option("blksize","16");option("blksize","16");request_send();error(8);
    rrq(path);option("seek","18446744073709551616");request_send();error(8);
    rrq(path);option("unknown","1");request_send();error(8);
    rrq(path);option("tsize","1");request_send();error(8);
    rrq(path);length--;request_send();error(8);
    rrq(path);text("blksize");request_send();error(8);
    rrq(path);missing=true;request_send();error(1);missing=false;
    rrq(path);option("tsize","0");fail_send=true;request_send();fail_send=false;assert(!packets);
    rrq(path);option("tsize","0");request_send();unsigned previous=closes;
    request_send();assert(closes==previous+1);reset_output();
    uint8_t a[]={0,4,0,0};tftp_data(reader(),2,120,a,4);assert(!packets);
    ack(2);assert(!packets);end();
    rrq("/readwrite/server_check.txt");request_send();error(1);
    rrq("readwrite/server_check.txt");request[1]=2;request_send();assert(packets==1&&output[0][1]==4&&output[0][3]==0);reset_output();
    uint8_t check[]={0,3,0,1,'t','e','s','t'};
    tftp_data(reader(),0,120,check,sizeof(check));assert(packets==1&&output[0][1]==4&&output[0][3]==1);reset_output();
    assert(tftp_check_exists&&tftp_check_size==4&&!memcmp(tftp_check,"test",4));
    rrq("/readwrite/server_check.txt");request_send();assert(packets==1&&output_size[0]==8&&!memcmp(output[0]+4,"test",4));ack(1);reset_output();
    rrq("/readwrite/server_check.txt");request[1]=2;option("blksize","8");option("wsize","10");option("tsize","16");request_send();
    assert(reader()->writing&&reader()->window==1);reset_output();
    uint8_t block[]={0,3,0,1,1,2,3,4,5,6,7,8};
    tftp_data(reader(),0,120,block,sizeof(block));tftp_data(reader(),0,120,block,sizeof(block));assert(tftp_check_size==8);reset_output();
    block[3]=2;tftp_data(reader(),0,120,block,sizeof(block));assert(tftp_check_size==16);reset_output();
    block[3]=3;tftp_data(reader(),0,120,block,4);assert(tftp_check_exists&&tftp_check_size==16);reset_output();
    rrq("/readwrite/server_check.txt");request[1]=2;option("tsize","4097");request_send();error(8);
    rrq("/readwrite/server_check.txt");request[1]=2;option("seek","1");request_send();error(8);
    rrq("/readwrite/server_check.txt");request[1]=2;option("rsize","1");request_send();error(8);
    rrq("/readwrite/server_check.txt");request[1]=2;option("blksize","7680");request_send();reset_output();
    uint8_t too_big[4101]={0,3,0,1};tftp_data(reader(),0,120,too_big,sizeof(too_big));error(3);
    rrq("/readwrite/other.txt");request[1]=2;request_send();error(2);
    puts("PASS: TFTP reads, RAM-only server_check writes, duplicate DATA, windows, partial reads, EOF, path allowlist, malformed/overflow options, failed sends and wrong peers");
}
'''
# The real structure uses the port's number to publish its service.
code=code.replace('unsigned used; void *context;', 'unsigned used; unsigned number; void *context;').replace('ports[i].used=1;ports[i].context', 'ports[i].used=1;ports[i].number=i+16384;ports[i].context')
with tempfile.TemporaryDirectory(prefix='wifi-tftp-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
