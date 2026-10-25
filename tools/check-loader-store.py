#!/usr/bin/env python3
"""Test the actual per-phone partition identity checks; no storage commands are sent."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'xnuloader/loader.c').read_text()
defines = '\n'.join(l for l in source.splitlines() if re.match(r'#define BLOCK_(DARWIN|RAPHAEL|WRITE_FIRST)', l))
function = re.search(r'static int\nblock_is_store\(.*?\n\}', source, re.S)[0]
test = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef struct { uint32_t a; uint16_t b, c; uint8_t d[8]; } efi_guid;
typedef struct { efi_guid type_guid, unique_guid; uint64_t start_lba, end_lba; } efi_partition_info;
typedef struct { struct { int read_only; } *media; } efi_block_io;
struct loader_block_part { char name[36]; unsigned unit, block_size; uint64_t blocks; };
static int platform_raphael, platform_redwood;
static int *PLAT;
static size_t str_len(const char *s) { return strlen(s); }
#define print(...) ((void)0)
''' + defines + '\n' + function + r'''
int main(void) {
    static const efi_guid types[] = {BLOCK_DARWIN_TYPE, BLOCK_RAPHAEL_TYPE};
    static const efi_guid unique[] = {BLOCK_DARWIN_UNIQ, BLOCK_RAPHAEL_UNIQ};
    static const uint64_t first[] = {BLOCK_DARWIN_FIRST, BLOCK_RAPHAEL_FIRST};
    static const uint64_t last[] = {BLOCK_DARWIN_LAST, BLOCK_RAPHAEL_LAST};
    static const char *names[] = {"darwin", "userdata"};
    for (unsigned target = 0; target < 2; target++) {
        PLAT = target ? &platform_raphael : &platform_redwood;
        efi_partition_info good = {types[target], unique[target], first[target], last[target]};
        struct loader_block_part bp = {.unit = 0, .block_size = 4096, .blocks = last[target]-first[target]+1};
        strcpy(bp.name, names[target]);
        typeof(*((efi_block_io *)0)->media) media = {0}; efi_block_io bio = {&media};
        assert(block_is_store(&good, &bio, &bp));
        for (unsigned byte = 0; byte < 16; byte++) {
            efi_partition_info bad = good; ((char *)&bad.type_guid)[byte] ^= 1;
            assert(!block_is_store(&bad, &bio, &bp));
            bad = good; ((char *)&bad.unique_guid)[byte] ^= 1;
            assert(!block_is_store(&bad, &bio, &bp));
        }
        efi_partition_info bad = good; bad.start_lba--; assert(!block_is_store(&bad, &bio, &bp));
        bad = good; bad.end_lba++; assert(!block_is_store(&bad, &bio, &bp));
        bp.unit = 1; assert(!block_is_store(&good, &bio, &bp)); bp.unit = 0;
        bp.block_size = 512; assert(!block_is_store(&good, &bio, &bp)); bp.block_size = 4096;
        bp.blocks--; assert(!block_is_store(&good, &bio, &bp)); bp.blocks++;
        media.read_only = 1; assert(!block_is_store(&good, &bio, &bp)); media.read_only = 0;
        strcat(bp.name, "x"); assert(!block_is_store(&good, &bio, &bp));
        strcpy(bp.name, "boot"); assert(!block_is_store(&good, &bio, &bp));
        strcpy(bp.name, names[1-target]); assert(!block_is_store(&good, &bio, &bp));
        /* Both fixed data slots are beyond the protected system region and inside the partition. */
        assert(BLOCK_WRITE_FIRST * 4096 <= 8589934592ULL);
        assert(8589934592ULL + 2 * 0x80000000ULL <= (last[target]-first[target]+1)*4096);
    }
}
'''
with tempfile.TemporaryDirectory(prefix='hackios-store-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
print('PASS: actual redwood/raphael store GUIDs, geometry, unit, size, mode and protected regions (ASan/UBSan)')
