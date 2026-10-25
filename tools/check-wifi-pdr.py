#!/usr/bin/env python3
"""Check the actual WLAN PDR subscription and acknowledgement messages."""
from pathlib import Path
import re
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f='\n'.join(re.search(r'static (?:const uint8_t \*|uint32_t)\n'+name+r'\(.*?\n\}',s,re.S)[0] for name in ('qmi_field','qmi_number'))
pdr=s[s.index('#define WLAN_DOMAIN'):s.index('static void\npd_mapper_start(void)')]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __unused __attribute__((unused))
struct hakios_qrtr_port { int unused; } port;
static uint8_t sent_data[64];static size_t sent_size;static unsigned sent,lookups;
static int qrtr_send(struct hakios_qrtr_port *p,uint32_t node,uint32_t remote,const void *data,size_t size) {
 assert(p==&port&&node==0&&remote==2&&size<=64);memcpy(sent_data,data,size);sent_size=size;sent++;return 0;
}
static struct hakios_qrtr_port *qrtr_open(void *receive,void *service,void *context) { assert(receive&&service&&!context);return &port; }
static int qrtr_lookup(struct hakios_qrtr_port *p,unsigned svc,unsigned ver,unsigned inst) { assert(p==&port&&svc==0x42&&ver==1&&inst==180);lookups++;return 0; }
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
'''+f+'\n'+pdr+r'''
int main(void) {
 wlan_pdr_start();assert(lookups==1);wlan_pdr_service(NULL,true,0x42,1,180,0,2);assert(sent==1);
 size_t n;const uint8_t *enable=qmi_field(sent_data,sent_size,1,&n);assert(enable&&n==1&&enable[0]==1);
 const uint8_t *name=qmi_field(sent_data,sent_size,2,&n);assert(name&&n==sizeof(WLAN_DOMAIN)-1&&!memcmp(name,WLAN_DOMAIN,n));
 uint8_t update[64]={4,0,0,0x22,0,0,0,1,4,0,0xff,0xff,0xff,0x1f,2,sizeof(WLAN_DOMAIN)-1,0};
 memcpy(update+17,WLAN_DOMAIN,sizeof(WLAN_DOMAIN)-1);size_t length=17+sizeof(WLAN_DOMAIN)-1;
 update[length++]=3;update[length++]=2;update[length++]=0;update[length++]=0x34;update[length++]=0x12;update[5]=length-7;
 wlan_pdr_receive(NULL,0,2,update,length);assert(sent==2&&sent_data[0]==0&&sent_data[3]==0x23);
 const uint8_t *txn=qmi_field(sent_data,sent_size,2,&n);assert(txn&&n==2&&txn[0]==0x34&&txn[1]==0x12);
 name=qmi_field(sent_data,sent_size,1,&n);assert(name&&n==sizeof(WLAN_DOMAIN)-1&&!memcmp(name,WLAN_DOMAIN,n));
 wlan_pdr_receive(NULL,1,2,update,length);assert(sent==2);
 update[5]--;wlan_pdr_receive(NULL,0,2,update,length);assert(sent==2);update[5]++;
 update[17]='x';wlan_pdr_receive(NULL,0,2,update,length);assert(sent==2);
 wlan_pdr_service(NULL,true,0x42,1,181,0,2);assert(sent==2);
 puts("PASS: WLAN PDR lookup, subscription, indication ACK and invalid peer/message rejection");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-pdr-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
