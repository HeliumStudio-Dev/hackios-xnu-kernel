#!/usr/bin/env python3
"""Build SM8150 ath10k and SAE on the existing LinuxKPI, or run the SAE host checks."""
from pathlib import Path
import argparse
import concurrent.futures
import hashlib
import os
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / 'xnu-deps/build/ath10k'
W = ROOT / 'wifi/lx'
CACHE = B / 'cache'
SOURCES = {
    'linux': ('linux-7.0.14.tar.xz', 'https://cdn.kernel.org/pub/linux/kernel/v7.x/linux-7.0.14.tar.xz',
              'de9999b784d2293f00d39c62d8f92a08ab8a54bc4e80ffd250a0c09cb07a0f98'),
    'freebsd': ('freebsd-15.1-src.txz', 'https://download.freebsd.org/releases/amd64/15.1-RELEASE/src.txz',
                'cf5762da53fd52e1eaf0f9ceee9bf58cbe314c821031d0d9ffa76823185a89e1'),
    'hostap': ('wpa_supplicant-2.11.tar.gz', 'https://w1.fi/releases/wpa_supplicant-2.11.tar.gz',
               '912ea06f74e30a8e36fbb68064d6cdff218d8d591db0fc5d75dee6c81ac7fc0a'),
    'mbedtls': ('mbedtls-3.6.7.tar.bz2', 'https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2',
                'a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6'),
}


def run(args, **kw):
    return subprocess.run([str(x) for x in args], check=True, **kw)


def archive(name):
    filename, url, sha = SOURCES[name]
    p = CACHE / filename
    if not p.exists():
        tmp = p.with_suffix(p.suffix + '.partial')
        run(['curl', '--fail', '--location', '--max-time', '180', url, '-o', tmp])
        tmp.replace(p)
    if hashlib.file_digest(p.open('rb'), 'sha256').hexdigest() != sha:
        raise RuntimeError(f'Checksum mismatch: {p}')
    return p


def extract(name, strip=1, members=(), patches=()):
    p = archive(name)
    out = B / name
    stamp = SOURCES[name][2] + repr((strip, members)) + hashlib.sha256(b''.join(p.read_bytes() for p in patches)).hexdigest()
    if (out / '.source').exists() and (out / '.source').read_text() == stamp:
        return out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    run(['tar', '-xf', p, '-C', out, f'--strip-components={strip}', *members])
    for patch in patches:
        run(['patch', '-s', '--no-backup-if-mismatch', '-d', out, '-p1', '-i', patch])
    (out / '.source').write_text(stamp)
    return out


def compile_all(jobs):
    def compile_one(job):
        source, obj, flags = job
        command = [*flags, '-MMD', '-MF', str(obj) + '.d', '-c', source, '-o', obj]
        record = obj.with_suffix('.command')
        if obj.exists() and record.exists() and record.read_text() == shlex.join(map(str, command)):
            deps = Path(str(obj) + '.d').read_text().replace('\\\n', ' ').split(':', 1)[1].split()
            if all(Path(p).exists() and Path(p).stat().st_mtime <= obj.stat().st_mtime for p in deps):
                return
        result = subprocess.run(list(map(str, command)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        obj.with_suffix('.err').write_bytes(result.stdout)
        if result.returncode:
            obj.unlink(missing_ok=True)
            raise RuntimeError(f'{source}:\n{result.stdout.decode(errors="replace")}')
        record.write_text(shlex.join(map(str, command)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(compile_one, jobs))


def sae_build(host):
    h, m = extract('hostap'), extract('mbedtls')
    out = B / ('sae-host' if host else 'sae-kernel')
    out.mkdir(exist_ok=True)
    flags = shlex.split(os.environ.get('HOSTCC', 'cc') if host else os.environ.get('CC', 'clang'))
    flags += ['-O2', '-g', '-std=gnu11', '-fno-strict-aliasing', '-DCONFIG_SAE', '-DCONFIG_ECC',
              '-DCONFIG_NO_STDOUT_DEBUG', '-DCONFIG_NO_WPA_MSG', '-DCONFIG_NO_RANDOM_POOL',
              f'-DMBEDTLS_CONFIG_FILE="{W}/sae/mbedtls_config.h"', '-include', str(W / 'sae/platform.h')]
    flags += [f'-I{p}' for p in [W / 'sae', h / 'src', h / 'src/utils', m / 'include', m / 'library']]
    if host:
        flags += ['-DLX_SAE_HOST', '-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    else:
        sdk = Path(os.environ.get('THEOS', str(Path.home() / 'theos'))) / 'sdks/iPhoneOS16.5.sdk'
        flags += ['-target', 'arm64-apple-ios16.5', '-isysroot', str(sdk), '-mkernel', '-mgeneral-regs-only',
                  '-ffreestanding', '-fno-builtin', '-D_FORTIFY_SOURCE=0',
                  f'-DLX_HAKIOS_LX_H="{ROOT}/xnu/files/bsd/sys/hakios.lx.h"']
    files = [m / 'library' / f'{n}.c' for n in
             'bignum bignum_core bignum_mod bignum_mod_raw constant_time ecp ecp_curves platform platform_util sha256 aes cipher cipher_wrap cmac'.split()]
    files += [h / 'src' / f'{n}.c' for n in
              'common/sae common/dragonfly crypto/sha256 crypto/sha256-prf crypto/sha256-kdf utils/wpabuf'.split()]
    files += [W / 'sae' / f'{n}.c' for n in 'platform crypto sae'.split()]
    jobs = [(p, out / f'{i}-{p.stem}.o', flags) for i, p in enumerate(files)]
    compile_all(jobs)
    return [obj for _, obj, _ in jobs], flags


def driver_build():
    parts = 'compat/linuxkpi sys arm64/include net net80211 netinet netinet6 vm kern tools libkern ddb security fs/pseudofs crypto opencrypto geom bsm isa cam rpc xdr x86/include ofed/include dev/pci dev/ofw dev/fdt dev/acpica dev/usb dev/iicbus dev/backlight contrib/ck/include contrib/dev/acpica/include contrib/libnv'.split()
    patch_files = sorted((W / 'patches').glob('*.patch'))
    f = extract('freebsd', 2, ['usr/src/COPYRIGHT', *[f'usr/src/sys/{p}' for p in parts]], patch_files)
    s, gen = f / 'sys', B / 'gen'
    gen.mkdir(exist_ok=True)
    if not (gen / 'machine').exists():
        (gen / 'machine').symlink_to(s / 'arm64/include')
    for p in 'kern/device_if.m kern/bus_if.m dev/pci/pci_if.m dev/pci/pci_iov_if.m dev/pci/pcib_if.m dev/iicbus/iicbus_if.m dev/iicbus/iicbb_if.m dev/backlight/backlight_if.m dev/usb/usb_if.m dev/ofw/ofw_bus_if.m'.split():
        run(['awk', '-f', s / 'tools/makeobjops.awk', s / p, '-h'], cwd=gen)
    for mode in 'hpq':
        run(['awk', '-f', s / 'tools/vnode_if.awk', s / 'kern/vnode_if.src', f'-{mode}'], cwd=gen)
    options = subprocess.check_output(['rg', '-o', '--no-filename', r'opt_[a-z0-9_]+\.h', s], text=True).split()
    for name in set(options + ['lkpi_iic_if.h']):
        (gen / name).touch()
    (gen / 'opt_global.h').write_text('#define SMP 1\n')
    (gen / 'opt_inet.h').write_text('#define INET 1\n#define INET6 1\n')
    (gen / 'opt_inet6.h').write_text('#define INET6 1\n')
    linux = extract('linux', 5, ['linux-7.0.14/drivers/net/wireless/ath/ath10k',
                               'linux-7.0.14/drivers/net/wireless/ath/regd.c',
                               'linux-7.0.14/drivers/net/wireless/ath/regd.h',
                               'linux-7.0.14/drivers/net/wireless/ath/regd_common.h',
                               'linux-7.0.14/drivers/net/wireless/ath/dfs_pattern_detector.h',
                               'linux-7.0.14/drivers/net/wireless/ath/spectral_common.h',
                               'linux-7.0.14/drivers/net/wireless/ath/ath.h'], [W / 'ath10k/patches/icnss-bootstrap.patch'])
    objdir = B / 'obj'; objdir.mkdir(exist_ok=True)
    flags = shlex.split(os.environ.get('CC', 'clang')) + ['-target', 'arm64-apple-ios16.5', '-mkernel',
        '-mgeneral-regs-only', '-fno-builtin', '-fno-common', '-ffreestanding', '-fno-strict-aliasing',
        '-funsigned-char', '-nostdinc', '-std=gnu17', '-O2', '-g', '-w', '-D__FreeBSD__=15', '-D_KERNEL',
        '-DKLD_MODULE', '-DHAVE_KERNEL_OPTION_HEADERS', '-include', str(gen / 'opt_global.h'),
        '-include', str(s / 'compat/linuxkpi/common/include/linux/kconfig.h'), '-DLINUXKPI_VERSION=70000', '-U__APPLE__',
        '-include', str(W / 'include/lx_prelude.h'), '-include', str(W / 'ath10k/include/ath10k_prelude.h'),
        '-DCONFIG_ATH10K_SNOC', '-DCONFIG_ATH10K_DEBUG', '-DLX_HAVE_SAE', '-DKBUILD_MODNAME="ath10k"',
        f'-DLX_HAKIOS_LX_H="{ROOT}/xnu/files/bsd/sys/hakios.lx.h"', f'-DLX_HAKIOS_QMI_H="{ROOT}/xnu/files/bsd/sys/hakios.qmi.h"']
    flags += [f'-I{p}' for p in [W / 'ath10k/include', W / 'include', W / 'src', W / 'sae', gen, s,
              s / 'contrib/ck/include', s / 'compat/linuxkpi/common/include', s / 'compat/linuxkpi/dummy/include',
              linux / 'ath10k', linux]]
    files = [linux / 'ath10k' / f'{n}.c' for n in
             'core ce hw htc htt htt_rx htt_tx mac wmi wmi-tlv bmi p2p swap txrx snoc qmi qmi_wlfw_v01 debug'.split()]
    files += [linux / 'regd.c', W / 'ath10k/host.c', *[W / 'src' / f'{n}.c' for n in 'lx_base lx_80211 lx_wpa'.split()]]
    table = []
    for i in range(256):
        value = i
        for _ in range(8):
            value = (value >> 1) ^ (0xedb88320 if value & 1 else 0)
        table.append(str(value))
    (gen / 'crc.c').write_text('const unsigned crc32_tab[256]={' + ','.join(table) + '};\n')
    files.append(gen / 'crc.c')
    jobs = [(p, objdir / f'{i}-{p.stem}.o', flags) for i, p in enumerate(files)]
    compile_all(jobs)
    return [obj for _, obj, _ in jobs]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sae-test', action='store_true')
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    if args.sae_test:
        objects, flags = sae_build(True)
        exe = B / 'sae-test'
        fixture = B / 'sae-host/wpa3.inc'
        with fixture.open('wb') as output:
            run(['python3', ROOT / 'tools/wpa-test/reference_wpa3.py'], stdout=output)
        run([*flags, f'-I{fixture.parent}', ROOT / 'tools/wpa-test/test_sae.c', *objects, '-o', exe])
        run([exe])
        run([*flags, '-DLX_HAVE_SAE', f'-I{W}/src', f'-I{fixture.parent}',
             ROOT / 'tools/wpa-test/test_wpa3.c', W / 'src/lx_wpa.c', *objects, '-o', B / 'wpa3-test'])
        run([B / 'wpa3-test'])
        return
    objects = driver_build()
    crypto, _ = sae_build(False)
    out = B / 'out'; out.mkdir(exist_ok=True)
    ld = ROOT / 'xnu-deps/host/bin/ld64'
    run([ld, '-r', '-arch', 'arm64', *objects, *crypto, '-o', out / 'all.o'])
    symbols = subprocess.check_output([ROOT / 'xnu-deps/host/bin/nm', '-u', out / 'all.o'], text=True).split()
    libc = 'memcmp memcpy memmove memset strcmp strncmp strlen strnlen strchr strrchr strlcpy strlcat bzero snprintf vsnprintf __stack_chk_fail __stack_chk_guard'.split()
    missing = [x for x in symbols if x.lstrip('_') not in [n.lstrip('_') for n in libc] and not x.startswith(('_lx_os_', '_qmi_', '_hakios_qmi_', 'section$'))]
    if missing:
        raise RuntimeError(f'Undefined symbols (no success stubs are generated): {missing}')
    (out / 'exported.txt').write_text('_lx_prepare\n_lx_start\n_lx_stop\n_lx_transmit\n')
    run([ld, '-r', '-arch', 'arm64', '-exported_symbols_list', out / 'exported.txt', out / 'all.o', '-o', out / 'ath10k.o'])
    print(out / 'ath10k.o')


if __name__ == '__main__':
    main()
