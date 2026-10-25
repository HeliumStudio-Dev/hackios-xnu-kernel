#!/usr/bin/env python3
"""Verify the actual board PD directory QMI encoding, pagination and malformed inputs."""
from pathlib import Path
import re
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
f='\n'.join(re.search(r'static (?:const uint8_t \*|uint32_t)\n'+name+r'\(.*?\n\}',s,re.S)[0] for name in ('qmi_field','qmi_number'))
pd=s[s.index('static struct hakios_qrtr_port *pd_mapper_port;'):s.index('#define WLAN_DOMAIN')]
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __unused __attribute__((unused))
struct hakios_qrtr_port { int unused; } port;
static uint32_t qrtr_peer;
static uint8_t answer[1024];
static size_t answer_size;
static unsigned sent;
static int qrtr_send(struct hakios_qrtr_port *p,uint32_t node,uint32_t remote,const void *data,size_t size) {
 assert(p==&port&&node==0&&remote==10&&size<=sizeof(answer));memcpy(answer,data,size);answer_size=size;sent++;return 0;
}
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
'''+f+pd+r'''
static uint8_t request[256];static size_t length;
static void tlv(unsigned type,const void *data,size_t size) {
 request[length++]=type;request[length++]=size;request[length++]=size>>8;memcpy(request+length,data,size);length+=size;
}
static void lookup(const char *name) {
 memset(request,0,sizeof(request));request[1]=7;request[3]=0x21;length=7;tlv(1,name,strlen(name));
}
static void send_request(bool success) {
 request[5]=length-7;request[6]=(length-7)>>8;unsigned before=sent;
 pd_mapper_request(NULL,0,10,request,length);assert(sent==before+1&&answer[1]==7&&answer[3]==0x21);
 size_t size;const uint8_t *result=qmi_field(answer,answer_size,2,&size);
 assert(result&&size==4&&((result[0]==0&&result[2]==0)==success));
 assert((size_t)(answer[5]|answer[6]<<8)==answer_size-7);
}
static void entry(const char *service,const char *domain,uint32_t instance) {
 lookup(service);send_request(true);size_t size;
 const uint8_t *total=qmi_field(answer,answer_size,0x10,&size);assert(total&&size==2&&total[0]==1&&total[1]==0);
 const uint8_t *list=qmi_field(answer,answer_size,0x12,&size);size_t n=strlen(domain);
 assert(list&&list[0]==1&&list[1]==n&&size==1+1+n+9&&!memcmp(list+2,domain,n));
 assert(qmi_number(list+2+n)==instance&&list[6+n]==0&&qmi_number(list+7+n)==0);
}
int main(void) {
 pd_mapper_port=&port;
 entry("kernel/elf_loader","msm/modem/wlan_pd",180);
 entry("wlan/fw","msm/modem/wlan_pd",180);
 entry("tms/pdr_enabled","msm/modem/root_pd",180);
 entry("avs/audio","msm/adsp/audio_pd",74);
 lookup("tms/servreg");send_request(true);size_t size;const uint8_t *list=qmi_field(answer,answer_size,0x12,&size);assert(list&&list[0]==7);
 lookup("tms/servreg");uint32_t offset=6;tlv(0x10,&offset,4);send_request(true);
 list=qmi_field(answer,answer_size,0x12,&size);assert(list&&list[0]==1);
 lookup("tms/servreg");offset=UINT32_MAX;tlv(0x10,&offset,4);send_request(true);assert(!qmi_field(answer,answer_size,0x12,&size));
 lookup("unknown");send_request(true);assert(!qmi_field(answer,answer_size,0x12,&size));
 lookup("wlan/fw");tlv(1,"wlan/fw",7);send_request(false);
 lookup("wlan/fw");tlv(0x10,&offset,3);send_request(false);
 lookup("wlan/fw");tlv(0x10,&offset,4);tlv(0x10,&offset,4);send_request(false);
 lookup("");send_request(false);
 lookup("wlan/fw");request[10]=0;send_request(false);
 lookup("wlan/fw");request[length++]=0x10;send_request(false);
 lookup("wlan/fw");unsigned before=sent;pd_mapper_request(NULL,1,10,request,length);assert(sent==before);
 puts("PASS: board PD mappings, QMI domain-list encoding, pagination, unknown service and malformed fields");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-pd-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
