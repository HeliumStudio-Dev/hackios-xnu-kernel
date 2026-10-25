#!/usr/bin/env python3
"""Exercise actual QRTR parsing and DEL_CLIENT for MPSS node zero."""
from pathlib import Path
import re
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f='\n'.join(re.search(r'static void\n'+n+r'\(.*?\n\}',s,re.S)[0] for n in ('qrtr_input','qrtr_close'))
control=re.search(r'static void\nqrtr_control\(.*?\n\}',s,re.S)[0].replace('qrtr_control(', 'qrtr_control_actual(',1)
structs=s[s.index('#define QRTR_US'):s.index('struct hakios_qrtr_port {')]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define bzero(p,n) memset(p,0,n)
typedef void (*hakios_qrtr_receive_t)(void*,uint32_t,uint32_t,const void*,size_t);
'''+structs+r'''
struct hakios_qrtr_port { uint32_t number;hakios_qrtr_receive_t receive;void *context; } qrtr_ports[16];
static uint32_t qrtr_peer,qrtr_in;static bool qrtr_peer_known;
static int qrtr_lock,qrtr_calling,link_thread_is;
static unsigned controls,callbacks,close_messages,notifications;static uint32_t qrtr_hellos;
static struct { uint32_t service,instance,node,port;bool there; } qrtr_servers[4];
static void qrtr_tell(uint32_t service,uint32_t instance,uint32_t node,uint32_t port,bool arrived) {(void)service;(void)instance;(void)node;(void)port;(void)arrived;notifications++;}
static int current_thread(void) { return 0; }
static void lck_mtx_lock(int *p) { assert(p==&qrtr_lock||p==&qrtr_calling); }
static void lck_mtx_unlock(int *p) { assert(p==&qrtr_lock||p==&qrtr_calling); }
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
static void qrtr_control(const struct qrtr_header *header,const struct qrtr_control *control) { assert(header&&control);controls++; }
static int qrtr_out_packet(uint32_t type,uint32_t from,uint32_t to,uint32_t port,const void *data,uint32_t size) {
 const struct qrtr_control *control=data;
 assert(type==QRTR_DEL_CLIENT&&from==123&&to==0&&port==QRTR_CONTROL&&size==sizeof(*control));
 assert(control->command==QRTR_DEL_CLIENT&&control->words[0]==QRTR_US&&control->words[1]==123);close_messages++;return 0;
}
static void receive(void *context,uint32_t node,uint32_t port,const void *data,size_t size) {
 assert(context==&callbacks&&node==0&&port==85&&size==1&&((const uint8_t*)data)[0]==0x42);callbacks++;
}
'''+f+'\n'+control+r'''
int main(void) {
 uint8_t packet[64]={0};struct qrtr_header *h=(void*)packet;
 *h=(struct qrtr_header){.version=1,.type=QRTR_DATA,.from_node=0,.from_port=85,.size=1,.to_node=1,.to_port=123};packet[32]=0x42;
 qrtr_ports[0]=(struct hakios_qrtr_port){.number=123,.receive=receive,.context=&callbacks};
 qrtr_input(packet,33);assert(callbacks==1&&qrtr_peer_known&&qrtr_peer==0);
 h->from_node=7;h->to_port=999;qrtr_input(packet,33);assert(qrtr_peer==0&&qrtr_peer_known&&callbacks==1);
 h->from_node=0;h->to_port=QRTR_CONTROL;qrtr_input(packet,33);assert(controls==0);
 h->size=4;packet[32]=QRTR_BYE;qrtr_input(packet,36);assert(controls==1);
 h->size=UINT32_MAX;qrtr_input(packet,33);assert(controls==1);
 h->size=2;qrtr_input(packet,33);assert(controls==1);
 h->size=0;qrtr_input(packet,33);assert(controls==1);
 h->size=8;packet[32]=QRTR_DEL_CLIENT;qrtr_input(packet,40);assert(controls==1);
 h->size=12;packet[32]=QRTR_NEW_SERVER;qrtr_input(packet,44);assert(controls==1);
 memset(packet,0,sizeof(packet));packet[0]=3;packet[1]=QRTR_DATA;packet[4]=1;packet[10]=85;packet[12]=1;packet[14]=123;packet[16]=0x42;
 qrtr_input(packet,17);assert(callbacks==2);
 packet[3]=255;qrtr_input(packet,17);assert(callbacks==2);
 qrtr_close(&qrtr_ports[0]);assert(close_messages==1&&qrtr_ports[0].number==0);
 qrtr_close(&qrtr_ports[0]);assert(close_messages==1);
 qrtr_servers[0].there=qrtr_servers[1].there=qrtr_servers[2].there=true;
 qrtr_servers[0].service=qrtr_servers[2].service=0x45;qrtr_servers[1].service=2;
 qrtr_servers[0].port=qrtr_servers[2].port=85;qrtr_servers[1].port=70;qrtr_servers[2].node=7;
 struct qrtr_control gone={.command=QRTR_DEL_CLIENT,.words={0,85}};
 struct qrtr_header header={.from_node=0};qrtr_control_actual(&header,&gone);
 assert(!qrtr_servers[0].there&&qrtr_servers[1].there&&qrtr_servers[2].there&&notifications==1);
 qrtr_control_actual(&header,&gone);assert(notifications==1);
 gone=(struct qrtr_control){.command=QRTR_DEL_SERVER,.words={0x45,1,7,85}};qrtr_control_actual(&header,&gone);
 assert(!qrtr_servers[2].there&&qrtr_servers[1].there&&notifications==2);
 gone.command=QRTR_BYE;qrtr_control_actual(&header,&gone);assert(!qrtr_servers[1].there&&notifications==3);
 puts("PASS: QRTR node-zero peer, v1/v2 bounds, overflow rejection, stable peer and DEL_CLIENT");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-qrtr-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
