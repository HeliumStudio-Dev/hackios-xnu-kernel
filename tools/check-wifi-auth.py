#!/usr/bin/env python3
"""Exercise the real RSN parser and SAE exchange control against malformed AP replies."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'wifi/lx/src/lx_80211.c').read_text()
def function(name, result):
    return re.search(r'static ' + result + r'\n' + name + r'\(.*?\n\}', source, re.S)[0]

code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define EAUTH 80
#define LX_HAVE_SAE
struct lx_target { uint8_t address[6],elements[256]; unsigned elements_length,capability; };
struct hakios_sta_join { uint8_t ssid[32],passphrase[64]; unsigned ssid_length,passphrase_length; };
struct vif { uint8_t addr[6]; };
struct lx_radio { struct vif *vif;struct lx_target target;bool h2e;unsigned auth_length;struct { uint8_t pmk[32]; } wpa;uint8_t pmkid[16]; };
struct lx_sae { int unused; } state;
static unsigned mode,commits,confirms,received,deleted;
static void lx_os_lock(void) { }
static void lx_os_unlock(void) { }
#define lx_tell(...) ((void)0)
#define explicit_bzero(p,n) memset(p,0,n)
static struct lx_sae *lx_sae_new(const void *a,const void *b,const void *c,unsigned d,const void *e,unsigned f,bool h) { return mode==1?NULL:&state; }
static int lx_sae_commit(struct lx_sae *s,const uint8_t *t,unsigned tn,uint8_t *out,unsigned *n) {
 assert(s==&state&&*n==1024);commits++;if(mode==2)return -1;
 if(mode==3&&commits==2)assert(tn==1&&t[0]==42);*n=98;return 0;
}
static bool sae_send(struct lx_radio *r,unsigned seq,unsigned status,const void *p,unsigned n) { assert((seq==1&&status==(r->h2e?126:0)&&n==98)||(seq==2&&!status&&n==34));return mode!=4; }
static unsigned sae_wait(struct lx_radio *r,uint8_t *p) {
 memset(p,0,1024);received++;
 if(mode==5)return 0;
 if((mode==3||mode==6||mode==7)&&received==1) {
  uint8_t token[]={1,0,76,0,19,0,255,2,93,42};memcpy(p,token,sizeof(token));
  if(!r->h2e) {p[6]=42;if(mode==6||mode==7)p[4]=20;return 7;}
  if(mode==6)p[7]=255;if(mode==7)p[8]=92;return sizeof(token);
 }
 p[0]=confirms?2:1;
 if(p[0]==1) { p[2]=r->h2e?126:0;if(mode==8)p[2]=77;return 102; }
 if(mode==9)p[2]=1;return 38;
}
static int lx_sae_accept_commit(struct lx_sae *s,const void *p,unsigned n) { assert(n==98);return mode==10?-1:0; }
static int lx_sae_confirm(struct lx_sae *s,void *p,unsigned *n) { confirms++;*n=34;return 0; }
static int lx_sae_accept_confirm(struct lx_sae *s,const void *p,unsigned n,void *pmk,void *id) { assert(n==34);return mode==11?-1:0; }
static void lx_sae_delete(struct lx_sae *s) { assert(s==&state);deleted++; }
''' + function('element', r'const uint8_t \*') + function('protection', r'const char \*') + function('sae_authenticate', 'int') + r'''
int main(void) {
 struct lx_target t={0};unsigned cipher;bool sae,h2e;
 const uint8_t rsn[]={48,26,1,0,0,15,172,4,1,0,0,15,172,4,1,0,0,15,172,8,192,0,0,0,0,15,172,6,244,1,32};
 memcpy(t.elements,rsn,sizeof(rsn));t.elements_length=sizeof(rsn);
 assert(!protection(&t,&cipher,&sae,&h2e)&&cipher==4&&sae&&h2e);
 t.elements[21]=0; t.elements[20]=0;assert(protection(&t,&cipher,&sae,&h2e));t.elements[20]=192;
 t.elements[22]=255;assert(protection(&t,&cipher,&sae,&h2e));t.elements[22]=0;
 t.elements[27]=7;assert(protection(&t,&cipher,&sae,&h2e));t.elements[27]=6;
 t.elements[8]=255;assert(protection(&t,&cipher,&sae,&h2e));t.elements[8]=1;
 t.elements[14]=255;assert(protection(&t,&cipher,&sae,&h2e));t.elements[14]=1;
 t.elements[1]=21;t.elements_length=23;assert(protection(&t,&cipher,&sae,&h2e));
 memcpy(t.elements,rsn,sizeof(rsn));t.elements[19]=2;t.elements[20]=0;t.elements_length=sizeof(rsn);
 assert(!protection(&t,&cipher,&sae,&h2e)&&!sae);
 for(unsigned n=0;n<20;n++) {t.elements_length=n;assert(protection(&t,&cipher,&sae,&h2e));}
 struct vif vif={0};struct lx_radio r={.vif=&vif};struct hakios_sta_join join={0};
 for(mode=0;mode<12;mode++) for(unsigned h=0;h<2;h++) {
  commits=confirms=received=deleted=0;r.h2e=h;
  int ret=sae_authenticate(&r,&join);
  assert(ret==((mode==0||mode==3)?0:mode==1?ENOMEM:mode==2||mode==4?EIO:mode==5?ETIMEDOUT:EAUTH));
  assert(deleted==(mode!=1));if(mode==5)assert(commits==5);
 }
 puts("PASS: RSN bounds, SAE/PMF selection, authentication retries, anti-clogging bounds and bad commit/confirm rejection");
}
'''
with tempfile.TemporaryDirectory(prefix='wifi-auth-') as tmp:
    p = Path(tmp)
    (p / 'check.c').write_text(code)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    str(p / 'check.c'), '-o', str(p / 'check')], check=True)
    subprocess.run([str(p / 'check')], check=True)
