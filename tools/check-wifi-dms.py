#!/usr/bin/env python3
"""Test native DMS address retrieval with the real QMI codec and transactions."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
function = re.search(r'static bool\nicnss_mac_address\(.*?\n\}', source, re.S)[0]
code = r'''
#include <sys/hakios.qmi.h>
#include <sys/hakios.qrtr.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
static unsigned opened,closed,sent,submitted,mode;
static bool icnss_mac_valid;
static uint8_t icnss_mac[6];
static int qrtr_lock;
#define lck_mtx_lock(p) ((void)(p))
#define lck_mtx_unlock(p) ((void)(p))
static struct { unsigned service,instance,node,port;bool there; } qrtr_servers[]={ {2,1,0,70,true} };
struct hakios_qrtr_port { hakios_qrtr_receive_t receive;void *context; } socket_port,board_port;
static struct hakios_qrtr_port *open_port(hakios_qrtr_receive_t rx,hakios_qrtr_server_t server,void *ctx) {
 (void)server;opened++;socket_port.receive=rx;socket_port.context=ctx;return &socket_port;
}
static void close_port(struct hakios_qrtr_port *p) {assert(p==&socket_port);closed++;}
static int send_packet(struct hakios_qrtr_port *p,uint32_t node,uint32_t remote,const void *data,size_t length) {
 const uint8_t *req=data;sent++;
 assert(p==&socket_port&&node==0&&remote==70&&length==14&&req[0]==0&&req[3]==0x5c&&!req[4]&&req[5]==7);
 const uint8_t body[]={1,4,0,0,0,0,0};assert(!memcmp(req+7,body,7));
 if(mode==1)return EIO;
 uint8_t reply[32]={2,req[1],req[2],0x5c,0,7,0,2,4,0,0,0,0,0};size_t size=14;
 if(mode==2){reply[10]=1;reply[12]=16;}
 else if(mode!=7){
  reply[14]=0x10;reply[15]=7;reply[17]=mode==3?8:mode==6?9:6;
  const uint8_t mac[]={2,0x11,0x22,0x33,0x44,0x55};memcpy(reply+18,mac,6);
  size=24;reply[5]=17;if(mode==4)reply[18]=1;if(mode==5)memset(reply+18,0,6);
 }
 socket_port.receive(socket_port.context,0,70,reply,size);return 0;
}
static bool icnss_call(struct hakios_qrtr_port *p,uint16_t message,const void *data,uint16_t length) {
 const uint8_t *bytes=data;const uint8_t mac[]={2,0x11,0x22,0x33,0x44,0x55};
 assert(p==&board_port&&message==0x33&&length==9&&bytes[0]==0x10&&bytes[1]==6&&!bytes[2]&&!memcmp(bytes+3,mac,6));
 submitted++;return mode!=8;
}
static void quiet_print(const char *s,...) {(void)s;}
#define printf quiet_print
''' + function + r'''
int main(void) {
 const struct hakios_qrtr_ops ops={.open=open_port,.send=send_packet,.close=close_port};
 hakios_qmi_set_transport(&ops);
 for(mode=0;mode<=8;mode++){
  icnss_mac_valid=false;unsigned before=sent,count=submitted;
  assert(icnss_mac_address(&board_port)==(mode==0));assert(opened==closed&&sent==before+1);
  assert(submitted==count+((mode==0||mode==8)?1:0));assert(icnss_mac_valid==(mode==0||mode==8));
 }
 mode=0;unsigned before=sent;assert(icnss_mac_address(&board_port)&&sent==before&&opened==closed);
 icnss_mac_valid=false;qrtr_servers[0].there=false;assert(!icnss_mac_address(&board_port)&&sent==before&&opened==closed);
 puts("PASS: native DMS WLAN MAC retrieval, validation, submission, cached retry, malformed replies and cleanup (real QMI)");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-dms-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined', '-pthread',
                    '-I' + str(root / 'xnu/files/bsd'), str(path / 'check.c'),
                    str(root / 'xnu/files/bsd/dev/hakios.qmi.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
