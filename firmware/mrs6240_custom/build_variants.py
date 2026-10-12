"""Build diagnostic images in an SDK copy; preserve failures and never flash."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from install_overlay import install

VARIANTS = {
    'both_side': (1,2,3,4),
    'single_side': (0,2,3,4),
    'full_range_both': (1,1,3,4),
    'full_range_single': (0,1,3,4),
    'long_integration': (1,2,4,4),
    'faster_presence': (1,2,3,2),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--variants',nargs='+',choices=VARIANTS,default=list(VARIANTS))
    args=parser.parse_args()
    sdk=args.sdk.resolve()
    project=sdk/'project/mmwave/mmwave_application/Posture/cdk_6240_cpuf'
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    try:
        for name in args.variants:
            folder=args.output/name
            folder.mkdir()
            mode,dec,interval,frame_dec=VARIANTS[name]
            install(sdk,mode,dec,interval,frame_dec)
            image=project/'output/mrs6240_p2512.img'
            before=image.stat().st_mtime_ns if image.exists() else None
            with (folder/'build.log').open('w') as log:
                proc=subprocess.run([str(args.compiler.resolve()),'-w','presence.cdkws','-c','psdf','-d','build','-v'],
                                    cwd=project,stdout=log,stderr=subprocess.STDOUT)
            log=(folder/'build.log').read_text(errors='replace')
            success=(proc.returncode==0 and 'image size (flash):' in log and
                     'sram size:' in log and image.exists() and image.stat().st_mtime_ns!=before)
            record=dict(name=name,cfar_mode=mode,range_dec=dec,interval_log2=interval,frame_dec=frame_dec,
                        exit_code=proc.returncode,packaged=success,flashed=False)
            if success:
                shutil.copyfile(image,folder/'candidate.img')
            for filename in ('prj_config.h','citraverse_runtime.c'):
                shutil.copyfile(project.parent/'src'/filename,folder/filename)
            record['files']={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                             for p in folder.iterdir() if p.is_file()}
            (folder/'manifest.json').write_text(json.dumps(record,indent=2))
            results.append(record)
            print(json.dumps({k:v for k,v in record.items() if k!='files'}),flush=True)
    finally:
        # Restore source defaults. Existing output must still be identified by its manifest.
        install(sdk,1,2,3)
        (args.output/'results.json').write_text(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
