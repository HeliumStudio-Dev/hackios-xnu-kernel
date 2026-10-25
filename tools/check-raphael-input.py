#!/usr/bin/env python3
"""Exercise the real board matcher and button initialization without accessing hardware."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]


def function(file, name):
    text = (root / 'xnu/files/bsd/dev' / file).read_text()
    return re.search(r'\n(?:int|void)\n' + name + r'\(void\)\n\{.*?\n\}', text, re.S).group()


source = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stddef.h>
#include <stdbool.h>
typedef void *DTEntry;
typedef void *thread_t;
#define kSuccess 0
#define KERN_SUCCESS 0
static const char *board = "redwood";
static unsigned property_size = 8;
static int lookup_error, property_error, enabled = 1, starts;
static struct { const char *name; uint16_t id; } pon = {"redwood", 0x013}, pin = {"redwood", 0x18d};
static uint8_t pon_subtype = 9, pon_power_mask = 0x80, pon_resin_mask = 0x40;
static int SecureDTLookupEntry(void *root, const char *path, DTEntry *out) {
    (void)root; assert(!strcmp(path, "/chosen")); *out = (void *)1; return lookup_error;
}
static int SecureDTGetProperty(DTEntry entry, const char *key, const void **out, unsigned *size) {
    assert(entry); assert(!strcmp(key, "hackios,platform"));
    *out = (void *)board; *size = property_size; return property_error;
}
static int PE_parse_boot_argn(const char *key, void *out, unsigned size) {
    (void)size; if (strcmp(key, "buttons")) return 0; *(uint32_t *)out = enabled; return 1;
}
static void buttons_thread(void *arg) { (void)arg; assert(0); }
static int kernel_thread_start(void (*fn)(void *), void *arg, thread_t *thread) {
    assert(fn == buttons_thread); assert((uintptr_t)arg == 5); *thread = (void *)2; starts++; return 0;
}
static void thread_deallocate(thread_t thread) { assert(thread == (void *)2); }
'''
source += function('hakios.input.c', 'hakios_is_raphael')
source += function('hakios.buttons.c', 'hakios_buttons_init')
source += r'''
int main(void) {
    assert(!hakios_is_raphael());
    hakios_buttons_init();
    assert(starts == 1 && pon.id == 0x013 && pin.id == 0x18d);
    assert(pon_subtype == 9 && pon_power_mask == 0x80 && pon_resin_mask == 0x40);
    board = "raphael";
    assert(hakios_is_raphael());
    lookup_error = -1; assert(!hakios_is_raphael()); lookup_error = 0;
    property_error = -1; assert(!hakios_is_raphael()); property_error = 0;
    property_size = 7; assert(!hakios_is_raphael()); property_size = 8;
    board = "raphaell"; assert(!hakios_is_raphael()); board = "raphael";
    enabled = 0; hakios_buttons_init(); assert(starts == 1 && pon.id == 0x013);
    enabled = 1; hakios_buttons_init();
    assert(starts == 2 && pon.id == 0x008 && pin.id == 0x0c5);
    assert(pon_subtype == 4 && pon_power_mask == 1 && pon_resin_mask == 2);
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-input-test-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(source)
    subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-o', str(path / 'test'), str(path / 'test.c')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('PASS: board matching, disabled input, redwood/raphael PMIC selection')
