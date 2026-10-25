#!/usr/bin/env python3
"""Exercise the loader's actual read-only USB block command against fake Block I/O."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnuloader/loader.c').read_text()
function = re.search(r'static void\nfb_read_part\(.*?\n\}', source, re.S)[0]
test = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define BLOCK_MAGIC 123u
#define BLOCK_MAX_PARTS 4u
#define BLOCK_BUFFER_SIZE 4096u
#define EFI_ERROR(s) ((s) != 0)
struct loader_block_part { char name[36]; uint32_t block_size; uint64_t blocks; };
static struct { uint64_t magic; unsigned parts; struct loader_block_part part[4]; } block_shared;
static char block_buffer[4096];
static const char *staged_data;
static uint64_t staged_len;
static unsigned reads;
static int idle = 1, fail;
static char reply[5];
static uint64_t last_lba, last_bytes;
typedef struct efi_block_io efi_block_io;
typedef uint64_t efi_status;
struct efi_block_io { struct { unsigned media_id; } *media;
    efi_status (*read_blocks)(efi_block_io *, unsigned, uint64_t, uint64_t, void *); };
static efi_status read_blocks(efi_block_io *bio, unsigned id, uint64_t lba, uint64_t bytes, void *buf) {
    (void)bio; (void)id; assert(buf == block_buffer); reads++; last_lba = lba; last_bytes = bytes;
    return fail;
}
static efi_block_io bio = {.read_blocks = read_blocks};
static efi_block_io *block_bios[4] = {&bio, &bio};
static void fb_reply(const char *status, const char *why) { (void)why; memcpy(reply, status, 5); }
static size_t str_len(const char *s) { return strlen(s); }
static int str_eq(const char *a, const char *b) { return !strcmp(a, b); }
static uint64_t parse_number(const char *s, unsigned base) { return strtoull(s, NULL, base); }
static int hc_list_is_uefis(void) { return idle; }
static void block_start(void) { assert(0); }
''' + function + r'''
static void ask(const char *s, int ok) {
    char command[128]; strcpy(command, s); fb_read_part(command);
    assert(!strcmp(reply, ok ? "OKAY" : "FAIL"));
    if (!ok) assert(staged_len == 0 && staged_data == NULL);
}
int main(void) {
    static typeof(*bio.media) media = {42}; bio.media = &media;
    block_shared.magic = BLOCK_MAGIC; block_shared.parts = 1;
    strcpy(block_shared.part[0].name, "userdata");
    block_shared.part[0].block_size = 512; block_shared.part[0].blocks = 32;
    ask("userdata 0 8", 1); assert(reads == 1 && staged_len == 4096 && last_lba == 0);
    ask("userdata 1f 1", 1); assert(reads == 2 && last_lba == 31 && last_bytes == 512);
    const char *bad[] = {"userdata 20 1", "userdata ffffffffffffffff 1", "userdata 1f 2",
        "userdata 0 ffffffffffffffff", "userdata 0 0", "userdata 0 9", "unknown 0 1",
        "userdata", "userdata 0", "userdata 0 1 extra", "userdata 0g 1", "userdata -1 1",
        "userdata 10000000000000000 1", "userdata  1", " 0 1", "userdata 0 "};
    for (unsigned i = 0; i < sizeof(bad)/sizeof(bad[0]); i++) ask(bad[i], 0);
    assert(reads == 2);
    idle = 0; ask("userdata 0 1", 0); assert(reads == 2); idle = 1;
    block_shared.part[0].block_size = 0; ask("userdata 0 1", 0); assert(reads == 2);
    block_shared.part[0].block_size = 512; fail = 1;
    ask("userdata 0 1", 0); assert(reads == 3); fail = 0;
    block_shared.part[1] = block_shared.part[0]; block_shared.parts = 2;
    ask("userdata 0 1", 0); assert(reads == 3);
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-read-part-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('PASS: read-part parsing, bounds, ambiguity, busy controller and I/O failures (ASan/UBSan)')
