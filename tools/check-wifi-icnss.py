#!/usr/bin/env python3
"""Run the actual ICNSS requests, reply matching and MSA validation against a fake firmware."""
from pathlib import Path
import re
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'xnu/files/bsd/dev/hakios.wifi.c').read_text()
names={'wlfw_service':'void','wlfw_receive':'void','qmi_field':'const uint8_t \\*','qmi_number':'uint32_t','icnss_call':'bool','icnss_default_board':'bool','icnss_bootstrap':'bool','icnss_board_data':'bool','icnss_memory_stop':'void'}
functions={n:re.search(r'static '+t+r'\n'+n+r'\(.*?\n\}',s,re.S)[0] for n,t in names.items()}
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __unused __attribute__((unused))
#define SERVICE_WLFW 0x45
struct hakios_qrtr_port { int unused; } port;
static struct hakios_qrtr_port board_port;
static unsigned open_ports;
static struct hakios_qrtr_port *qrtr_open(void *a,void *b,void *c) {(void)a;(void)b;(void)c;open_ports++;return &board_port;}
static void qrtr_close(struct hakios_qrtr_port *p) {assert(p==&board_port&&open_ports);open_ports--;}
struct smp2p { int unused; };
static bool dsp_words(struct smp2p *p) {(void)p;return false;}
static void show_words(const char *s,struct smp2p *p) {(void)s;(void)p;}
static void show_crash_reason(void) { }
static bool icnss_mac_address(struct hakios_qrtr_port *p) { (void)p;return true; }
static uint32_t wlfw_node,wlfw_port=85;
static volatile uint32_t wlfw_answer;
static uint8_t wlfw_answer_bytes[1024];
static uint16_t wlfw_transaction,wlfw_expected;
static volatile bool wlfw_ready,wlfw_msa_ready;
static volatile bool wlfw_rejuvenating;
static volatile bool raphael_wlan_crashed;
static void icnss_dump_strings(uint64_t address,uint32_t size) { (void)address;(void)size; }
static bool wlfw_connected;
static uint32_t wlfw_next_node,wlfw_next_port;
static uint64_t clock_us;
static unsigned sent,allocations,board_segments;
static uint8_t board_data[128*1024];
static uint64_t board_size=26328;
static bool board_missing;
#define Z_WAITOK 0
#define Z_ZERO 1
static void *kalloc_data(size_t size,int flags) { (void)flags;void *p=calloc(1,size);if(p)allocations++;return p; }
static void kfree_data(void *p,size_t size) { (void)size;assert(p&&allocations);allocations--;free(p); }
static int mode;
static bool PE_parse_boot_arg_str(const char *key,char *value,size_t size) {assert(!strcmp(key,"wifi_bdf")&&size==32);if(mode==24)return false;strcpy(value,mode==25?"../bdwlan.bin":mode==26?"bd_f11gl.bin":"bd_f11cn.bin");return true;}
static const uint8_t *image_file(const char *name,uint64_t *size) { assert(!strcmp(name,mode==26?"bd_f11gl.bin":"bd_f11cn.bin"));*size=board_size;return board_missing?NULL:board_data; }
static unsigned hakios_wifi_option(const char *name) { assert(!strcmp(name,"wifi_smmu"));return 2; }
static bool icnss_smmu_prepare(void) { return mode!=23; }
static void radio_space_faults(void) { }
static unsigned permissions;
static bool icnss_rails_touched;
static bool icnss_qdss_touched;
static bool hakios_is_raphael(void) { return true; }
static void icnss_rail_status(void) { }
static bool icnss_power(bool on) { icnss_rails_touched=on;return true; }
static bool scm_memory_permission(uint64_t addr,uint32_t size,uint32_t src,uint32_t dst,uint32_t perm) {
 assert(addr>=0x8bc00000&&addr+size<=0x8bd80000);
 if(perm==6) assert(src==(1u<<3)&&dst==((1u<<15)|(1u<<24)|(1u<<25)));
 else assert(perm==7&&dst==(1u<<3));
 permissions++;return true;
}
static void settle(void) { }
static uint64_t now_us(void) { return clock_us; }
static void sleep_us(unsigned us);
static void quiet_print(const char *s,...) { (void)s; }
#define printf quiet_print
'''+s[s.index('#define VM_HLOS'):s.index('/* qcom_scm_assign_mem:')]+functions['wlfw_service']+'\n'+functions['wlfw_receive']+'\n'+functions['qmi_field']+'\n'+functions['qmi_number']+r'''
static void sleep_us(unsigned us) { assert(us==1000);clock_us+=us;if(mode==22&&clock_us==5000)raphael_wlan_crashed=true;
 if(mode==21&&clock_us==5000){uint8_t recovery[]={4,0,0,0x39,0,4,0,0x10,1,0,2};wlfw_receive(NULL,0,85,recovery,sizeof(recovery));}
 if(mode>=17&&clock_us==10000)wlfw_service(NULL,true,0x45,1,0,0,92);if(mode==20&&clock_us==20000)wlfw_service(NULL,true,0x45,1,0,0,93); }

static int qrtr_send(struct hakios_qrtr_port *p,uint32_t node,uint32_t remote,const void *data,size_t size) {
 assert((p==&port||p==&board_port)&&node==0&&remote==wlfw_port);sent++;
 const uint8_t *request=data;
 unsigned message=request[3]|request[4]<<8;
 assert(size==7u+(request[5]|request[6]<<8)&&request[0]==0);
 if(mode==1)return 0;
 uint8_t response[64]={2,request[1],request[2],request[3],request[4],7,0,2,4,0,0,0,0,0};
 size_t length=14;
 if(message==0x20) {
  if(p==&board_port)board_segments=0;
  size_t n;const uint8_t *client=qmi_field(request,size,0x15,&n);
  assert(client&&n==4&&qmi_number(client)==(p==&port?0x4b4e454c:0x444d4f4e));
  const uint8_t *ready=qmi_field(request,size,0x13,&n);assert(ready&&n==1&&ready[0]==1);
  if(mode==2){response[10]=1;response[12]=90;}
  if(mode>=17&&mode<=18&&remote==92){response[14]=0x10;response[15]=mode==18?7:8;response[17]=2;length=25;response[5]=length-7;}
  if(mode==16&&p==&board_port){response[10]=1;response[12]=90;}
  if(mode>=11&&mode<=15){response[14]=0x10;response[15]=mode==13?7:8;response[17]=mode==11?2:mode==12?1:0;length=25;response[5]=length-7;if(mode==14)response[15]=9;if(mode==15){response[25]=0x10;response[26]=0;response[27]=0;length=28;response[5]=length-7;}}
 } else if(message==0x2d) {size_t n;uint64_t addr;
  const uint8_t *a=qmi_field(request,size,1,&n);assert(a&&n==8);memcpy(&addr,a,8);assert(addr==0x8bc00000);
  a=qmi_field(request,size,2,&n);assert(a&&n==4&&qmi_number(a)==0x180000);
  response[14]=3;response[15]=14;response[16]=0;response[17]=1;length=31;
  uint64_t region=0x8bc00000;uint32_t bytes=0x180000;
  if(mode==3)region--;
  if(mode==4)bytes++;
  if(mode==5)bytes=0;
  if(mode==6)region=UINT64_MAX;
  memcpy(response+18,&region,8);memcpy(response+26,&bytes,4);response[30]=mode==7?2:0;
  if(mode==8)response[17]=3;
  if(mode==9)length--;
  response[5]=length-7;
 }
 else if(message==0x25) {
  size_t n;const uint8_t *field=qmi_field(request,size,0x10,&n);assert(field&&n==4&&qmi_number(field)==0);
  field=qmi_field(request,size,0x15,&n);assert(field&&n==1&&*field==0);
  field=qmi_field(request,size,0x11,&n);assert(field&&n==4&&qmi_number(field)==board_size);
  field=qmi_field(request,size,0x12,&n);assert(field&&n==4&&qmi_number(field)==board_segments);
  field=qmi_field(request,size,0x13,&n);assert(field&&n>=2);unsigned bytes=field[0]|field[1]<<8;
  assert(n==bytes+2&&bytes<=6144&&!memcmp(field+2,board_data+6144*board_segments,bytes));
  field=qmi_field(request,size,0x14,&n);assert(field&&n==1&&field[0]==(6144*board_segments+bytes==board_size));
  board_segments++;
  if(mode==10){response[10]=1;response[12]=90;}
 } else {
  assert(message==0x2e||message==0x24||message==0x3b||message==0x26||message==0x3a);
  if(message==0x3a){assert(mode==21&&size==7);uint8_t ready[]={4,0,0,0x21,0,0,0};wlfw_receive(NULL,0,remote,ready,7);}
  if(message==0x26){assert(size==15);size_t n;const uint8_t *empty=qmi_field(request,size,1,&n);assert(empty&&n==1&&empty[0]==0);empty=qmi_field(request,size,0x11,&n);assert(empty&&n==1&&empty[0]==0);uint8_t ready[]={4,0,0,0x21,0,0,0};if(mode<17||(mode==19&&remote==92))wlfw_receive(NULL,0,remote,ready,7);}
 }
 uint8_t indication[]={4,0,0,0x2b,0,0,0};
 wlfw_receive(NULL,0,remote,indication,7);assert(wlfw_msa_ready&&!wlfw_answer);
 response[1]++;wlfw_receive(NULL,0,remote,response,length);assert(!wlfw_answer);response[1]--;
 wlfw_receive(NULL,1,85,response,length);assert(!wlfw_answer);
 wlfw_receive(NULL,0,remote,response,length);return 0;
}
'''+s[s.index('static struct { uint64_t address; uint32_t size, owners; } icnss_regions'):s.index('static void\nicnss_dump_strings')]+functions['icnss_memory_stop']+'\n'+functions['icnss_call']+'\n'+functions['icnss_board_data']+'\n'+functions['icnss_default_board']+'\n'+functions['icnss_bootstrap']+r'''
int main(void) {
 wlfw_service(NULL,true,0x45,1,0,0,92);assert(wlfw_port==92);wlfw_service(NULL,false,0x45,1,0,0,85);assert(wlfw_port==92);wlfw_service(NULL,true,0x45,1,0,0,85);
 wlfw_connected=true;
 wlfw_service(NULL,true,0x45,1,0,0,92);assert(wlfw_port==85);
 wlfw_service(NULL,false,0x45,1,0,0,92);assert(wlfw_port==85&&!wlfw_next_port);
 wlfw_service(NULL,false,0x45,1,0,0,85);assert(!wlfw_port);
 wlfw_service(NULL,true,0x45,1,0,0,92);assert(!wlfw_port&&wlfw_next_port==92);
 wlfw_connected=false;wlfw_service(NULL,true,0x45,1,0,0,92);assert(wlfw_port==92);
 wlfw_service(NULL,false,0x45,1,0,0,92);wlfw_service(NULL,true,0x45,1,0,0,85);assert(wlfw_port==85&&!wlfw_node);
 assert(icnss_bootstrap(&port)&&sent==13&&permissions==1&&board_segments==5&&!allocations&&!open_ports);icnss_memory_stop();assert(permissions==2&&!icnss_regions[0].owners);
 for(mode=1;mode<=9;mode++){sent=0;clock_us=0;assert(!icnss_bootstrap(&port));assert(sent==(mode<=2?1u:2u));if(mode==1)assert(clock_us==3000000);}
 mode=10;sent=board_segments=0;wlfw_ready=false;assert(!icnss_bootstrap(&port)&&sent==8&&board_segments==1&&!allocations&&!open_ports);icnss_memory_stop();
 for(mode=11;mode<=15;mode++){sent=0;wlfw_ready=false;assert(icnss_bootstrap(&port)==(mode==11));assert(sent==1&&!allocations);assert(wlfw_ready==(mode==11));}
 mode=16;sent=0;assert(!icnss_bootstrap(&port)&&sent==6&&!open_ports&&!allocations);icnss_memory_stop();
 for(mode=17;mode<=20;mode++){sent=board_segments=0;clock_us=0;wlfw_ready=false;wlfw_port=85;assert(icnss_bootstrap(&port)==(mode==17||mode==19));assert(sent==(mode<=18?14u:26u)&&!open_ports&&!allocations);icnss_memory_stop();}wlfw_port=85;
 mode=21;sent=board_segments=0;clock_us=0;wlfw_ready=false;assert(icnss_bootstrap(&port)&&sent==14&&!open_ports&&!allocations&&!wlfw_rejuvenating);icnss_memory_stop();
 mode=22;sent=board_segments=0;clock_us=0;wlfw_ready=false;wlfw_port=85;assert(!icnss_bootstrap(&port)&&sent==13&&!open_ports&&!allocations&&raphael_wlan_crashed);icnss_memory_stop();raphael_wlan_crashed=false;
 mode=23;sent=0;wlfw_ready=false;assert(!icnss_bootstrap(&port)&&sent==1&&!open_ports&&!allocations);
 for(mode=24;mode<=25;mode++){sent=0;assert(!icnss_board_data(&port)&&!sent&&!allocations);}
 mode=26;sent=board_segments=0;assert(icnss_board_data(&port)&&board_segments==5&&!allocations);
 mode=0;sent=board_segments=0;board_missing=true;assert(!icnss_board_data(&port)&&!sent&&!allocations);board_missing=false;
 board_size=0;assert(!icnss_board_data(&port)&&!sent&&!allocations);
 board_size=128*1024+1;assert(!icnss_board_data(&port)&&!sent&&!allocations);
 board_size=128*1024;assert(icnss_board_data(&port)&&board_segments==22&&!allocations);
 puts("PASS: native ICNSS registration/MSA/BDF/calibration, complete segmented payload, rejection cleanup, reply matching and invalid memory bounds");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-icnss-') as tmp:
 p=Path(tmp);(p/'check.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-O1','-g','-fsanitize=address,undefined',str(p/'check.c'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
