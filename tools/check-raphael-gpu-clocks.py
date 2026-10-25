#!/usr/bin/env python3
"""Check the actual HFI speeds and RPMh GFX/MX dependency votes, without hardware writes."""
from pathlib import Path
import re
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[1] / 'xnu/files/bsd/dev/hakios.adreno.c').read_text()
vote = re.search(r'static bool\nrail_vote\(.*?\n\}', source, re.S)[0]
body = source[source.index('step_core_power(void)'):]
speeds = re.search(r'const struct \{.*?\} speeds\[\] = .*?;', body, re.S)[0]
test = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
''' + vote + r'''
static void check(bool a640) {
''' + speeds + r'''
    const uint16_t gfx[] = {0,16,48,64,128,192,224,256,320,384,416};
    const uint16_t mx[] = {0,16,128,192,256,320,384,416};
    unsigned n = a640 ? sizeof(speeds) / sizeof(speeds[0]) : 4;
    uint32_t last = 0;
    assert(n <= 16);
    assert(speeds[1].khz == (a640 ? 257000 : 315000));
    assert(speeds[2].khz == (a640 ? 345000 : 450000));
    assert(speeds[3].khz == (a640 ? 427000 : 550000));
    for (unsigned i = 0; i < n; i++) {
        uint32_t v;
        assert(rail_vote(speeds[i].level, gfx, 11, mx, 8, &v));
        assert((v >> 16) >= speeds[i].level && mx[(v >> 8) & 255] >= (v >> 16));
        assert((v >> 16) >= last); last = v >> 16;
        if (i) assert(speeds[i].khz > speeds[i-1].khz);
    }
    if (a640) {
        uint32_t v;
        assert(n == 6 && speeds[4].khz == 585000 && speeds[5].khz == 765000);
        /* zundamon-miui OPP requests 164 and 310; RPMh rounds up to 192 and 320. */
        assert(rail_vote(164, gfx, 11, mx, 8, &v) && v == (192u << 16 | 3u << 8 | 5u));
        assert(rail_vote(310, gfx, 11, mx, 8, &v) && v == (320u << 16 | 5u << 8 | 8u));
        assert(!rail_vote(310, gfx, 8, mx, 8, &v));
        assert(!rail_vote(310, gfx, 11, mx, 5, &v));
        assert(!rail_vote(310, gfx, 11, mx, 0, &v));
    }
}
int main(void) { check(false); check(true); }
'''
with tempfile.TemporaryDirectory(prefix='hackios-gpu-clocks-') as tmp:
    path = Path(tmp)
    (path / 'check.c').write_text(test)
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    str(path / 'check.c'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
print('PASS: actual redwood/A640 HFI speeds, native/OC votes and missing GFX/MX levels (ASan/UBSan)')
