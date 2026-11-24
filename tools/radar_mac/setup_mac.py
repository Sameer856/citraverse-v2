#!/usr/bin/env python3
"""Download the official SDK separately, then build our adapter locally."""
import hashlib
import io
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
SDK_URL = 'https://file.wch.cn/download/file?id=525'
SDK_SHA256 = '12d9d9bee7b2803c54e2a99b7c1a1381b77b88c8b54aad89507c88ff34c77fcd'


def main():
    if platform.system() != 'Darwin':
        raise SystemExit('This package requires macOS 11 or later.')
    if sys.version_info < (3, 9):
        raise SystemExit('Install Python 3.9 or later from python.org first.')
    if subprocess.run(['xcrun', '--find', 'clang'], capture_output=True).returncode:
        raise SystemExit('Install Apple Command Line Tools (xcode-select --install), then run setup again.')
    build = ROOT / 'build'
    build.mkdir(exist_ok=True)
    sdk = ROOT / '.vendor'
    sdk.mkdir(exist_ok=True)
    archive = sdk / 'CH341PAR_MAC.zip'
    if len(sys.argv) > 1:
        shutil.copyfile(sys.argv[1], archive)
    if not archive.exists():
        print('Downloading WCH’s official Mac USB SPI SDK…', flush=True)
        temporary = archive.with_suffix('.download')
        subprocess.run(['curl', '-fL', '--max-time', '240', '--retry', '2', SDK_URL,
                        '-o', str(temporary)], check=True)
        temporary.rename(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SDK_SHA256:
        raise SystemExit('SDK checksum does not match the verified 1.0 archive. Remove .vendor/CH341PAR_MAC.zip and download it again from WCH; do not bypass this check.')
    with ZipFile(archive) as outer:
        name = next(n for n in outer.namelist() if n.endswith('/LIB/lib.zip'))
        with ZipFile(io.BytesIO(outer.read(name))) as inner:
            for filename in ('ch347_lib.h', 'Constant.h', 'libch347.a'):
                name = next(n for n in inner.namelist() if n.endswith('/' + filename))
                (sdk / filename).write_bytes(inner.read(name))
    print('Building the Mac USB adapter…', flush=True)
    subprocess.run(['xcrun', 'clang', '-dynamiclib', '-O2', '-mmacosx-version-min=11.0',
                    '-arch', 'arm64', '-arch', 'x86_64', str(ROOT / 'native/bridge.c'),
                    str(sdk / 'libch347.a'), '-I', str(sdk), '-framework', 'IOKit',
                    '-framework', 'CoreFoundation', '-framework', 'Foundation',
                    '-o', str(build / 'libcitra_ch347.dylib')], check=True)
    venv = ROOT / '.venv'
    if not (venv / 'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
    subprocess.run([str(venv / 'bin/python'), '-m', 'pip', 'install', 'pyserial==3.5'], check=True)
    print('Setup complete. Open Start Radar Mac.command. Live hardware validation is still pending.')


if __name__ == '__main__':
    main()
