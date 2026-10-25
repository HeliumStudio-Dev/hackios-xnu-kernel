#!/usr/bin/env python3
"""Check native DIAG server registration, bounded control parsing and F3 masks."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.wifi.c').read_text()
diag = source[source.index('static struct { struct hakios_qrtr_port *port; uint32_t remote; unsigned packets; bool configured; } mpss_diag'):source.index('static struct hakios_qrtr_port *pd_mapper_port;')]
diag = re.sub(r'static void\nmpss_microdump\(.*?\n\}', '', diag, flags=re.S)
number = re.search(r'static uint32_t\nqmi_number\(.*?\n\}', source, re.S)[0]
code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define QRTR_NEW_SERVER 4
#define QRTR_CONTROL 0xfffffffe
#define QRTR_US 1
struct hakios_qrtr_port {unsigned number;} ports[2];
struct qrtr_control {uint32_t command,words[4];};
static unsigned opened,published,sent,lines;
static unsigned closed,fail_open,fail_publish;
static unsigned expected_id;
static const char *expected_name;
static uint32_t qrtr_peer;
static struct hakios_qrtr_port *qrtr_open(void *receive,void *server,void *context) {
 assert(receive&&!server&&(uintptr_t)context==opened&&opened<2);if(fail_open==opened+1)return NULL;
 ports[opened].number=100+opened;return &ports[opened++];
}
static void qrtr_close(struct hakios_qrtr_port *p) {assert(p->number);p->number=0;closed++;}
static int qrtr_out_packet(unsigned type,unsigned from,unsigned node,unsigned to,const void *data,unsigned size) {
 const struct qrtr_control *p=data;
 assert(type==4&&from==QRTR_CONTROL&&node==0&&to==QRTR_CONTROL&&size==sizeof(*p));
 assert(p->command==4&&p->words[0]==0x1001&&p->words[1]==2*published&&p->words[2]==1&&p->words[3]==100+published);
 published++;return fail_publish==published?-1:0;
}
static int qrtr_send(struct hakios_qrtr_port *p,unsigned node,unsigned remote,const void *data,size_t size) {
 const uint8_t *b=data;assert(p==&ports[0]&&!node&&remote==31);
 if(sent==0)assert(size==14&&b[0]==8&&b[4]==6&&b[8]==2&&b[12]==0x41&&b[13]==0xa8);
 else if(b[0]==11)assert(size==23&&b[4]==15&&b[8]==1&&b[9]==2&&b[15]==1&&b[19]==0x18);
 else if(sent==2)assert(size==44&&b[0]==3&&b[4]==36&&b[8]==1&&b[12]==1&&b[16]==1);
 else if(b[0]==33)assert(size==17+strlen(expected_name)&&b[4]==size-8&&b[8]==1&&b[12]==expected_id&&!strcmp((const char*)b+16,expected_name));
 else assert(size==45&&b[0]==3&&b[4]==37&&b[8]==2&&b[12]==1&&b[16]==1&&b[44]==expected_id);
 sent++;return 0;
}
static void capture(const char *fmt,...) {(void)fmt;lines++;}
#define printf capture
''' + number + '\n' + diag + r'''
int main(void) {
 assert(mpss_diag_start()&&opened==2&&published==2);
 uint8_t feature[]={8,0,0,0,6,0,0,0,2,0,0,0,1,0x20};
 mpss_diag_receive(NULL,1,31,feature,sizeof(feature));assert(!sent&&!mpss_diag[0].remote);
 mpss_diag_receive(NULL,0,31,feature,0);assert(!sent);
 for(unsigned size=1;size<sizeof(feature);size++){mpss_diag_receive(NULL,0,31,feature,size);assert(!sent);}
 feature[8]=255;mpss_diag_receive(NULL,0,31,feature,sizeof(feature));assert(!sent);
 feature[8]=2;feature[4]=255;mpss_diag_receive(NULL,0,31,feature,sizeof(feature));assert(!sent);
 feature[4]=6;mpss_diag_receive(NULL,0,32,feature,sizeof(feature));assert(!sent);
 uint8_t combined[22]={0};memcpy(combined+8,feature,sizeof(feature));
 mpss_diag_receive(NULL,0,31,combined,sizeof(combined));assert(sent==3&&mpss_diag[0].configured);
 mpss_diag_receive(NULL,0,31,feature,sizeof(feature));assert(sent==3);
 uint8_t identity[46]={33,0,0,0,9,0,0,0,1,0,0,0};
 mpss_diag_receive(NULL,0,31,identity,17);assert(sent==3);
 for(unsigned i=0;i<9;i++) {
  char name[30];snprintf(name,sizeof(name),"msm/modem/pd%u",i);
  expected_name=name;expected_id=i+2;identity[4]=8+strlen(name)+1;strcpy((char*)identity+16,name);
  mpss_diag_receive(NULL,0,31,identity,8+identity[4]);assert(sent==(i<8?6+3*i:27));
 }
 expected_name="msm/modem/pd0";expected_id=2;identity[4]=8+strlen(expected_name)+1;strcpy((char*)identity+16,expected_name);
 mpss_diag_receive(NULL,0,31,identity,8+identity[4]);assert(sent==30);
 identity[8]=2;mpss_diag_receive(NULL,0,31,identity,8+identity[4]);assert(sent==30);identity[8]=1;
 identity[16]=1;mpss_diag_receive(NULL,0,31,identity,8+identity[4]);assert(sent==30);
 char message[192];memset(message,'A',sizeof(message));
 mpss_diag_receive((void*)1,0,33,message,0x4401);assert(!mpss_diag[1].packets);
 mpss_diag_receive((void*)1,0,33,message,sizeof(message));assert(mpss_diag[1].packets==1);
 unsigned before=lines;mpss_diag[1].packets=128;mpss_diag_receive((void*)1,0,33,message,sizeof(message));assert(lines==before);
 mpss_diag_receive((void*)2,0,31,feature,sizeof(feature));
 opened=published=closed=0;fail_open=2;assert(!mpss_diag_start()&&closed==1&&!mpss_diag[0].port);
 opened=published=closed=0;fail_open=0;fail_publish=2;assert(!mpss_diag_start()&&closed==2&&!mpss_diag[1].port);
 puts("PASS: native DIAG server instances, feature/F3 wire format, malformed lengths, peer pinning and bounded logging");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-diag-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
