"""Apply Citraverse callbacks to a disposable PSDF SDK 2.1.2 copy."""
import argparse
import pathlib
import re
import shutil

def replace_once(text, pattern, replacement):
    text, count = re.subn(pattern, lambda _: replacement, text, count=1)
    if count != 1:
        raise ValueError(f"SDK layout mismatch: {pattern}")
    return text

def install(sdk, cfar_mode=1, range_dec=2, interval_log2=3, frame_dec=4):
    if cfar_mode not in (0, 1):
        raise ValueError('CFAR mode must be 0 or 1')
    if range_dec not in (1,2) or interval_log2 not in (3,4) or frame_dec not in (2,4):
        raise ValueError('Unsupported experimental presence geometry')
    source = sdk / "project/mmwave/mmwave_application/Posture/src"
    entry = source / "mmw_app_entry.c"
    text = entry.read_text()
    if '#include "citraverse_runtime.c"' not in text:
        text = replace_once(text, r"__sram_text int mmw_frame_cb\([^}]+\}", '#include "citraverse_runtime.c"\n\n__sram_text int mmw_frame_cb(uint8_t argc, void* arg[]) {\n    return cv_frame(argc,arg);\n}')
        text = replace_once(text, r"int app_init_cb\(void\)\s*\{[^}]+\}", "int app_init_cb(void) {\n    cv_init();\n    return 0;\n}")
        entry.write_text(text)
    main = source / "main.c"
    text = main.read_text()
    if "extern int cv_config" not in text:
        text = replace_once(text, r"extern int app_init_cb\(void\);", "extern int cv_config(HIF_MsgHdr_t *msg);\nextern int cv_read(HIF_MsgHdr_t *msg);\nextern int app_init_cb(void);")
    text = replace_once(text, r"\.mmw_hif_config_handler\s*=\s*\w+", ".mmw_hif_config_handler = cv_config")
    text = replace_once(text, r"\.mmw_hif_report_handler\s*=\s*\w+", ".mmw_hif_report_handler = cv_read")
    main.write_text(text)
    config = source / "prj_config.h"
    text = config.read_text()
    name = "CONFIG_MMW_MICRO_POINT_CLOUD_CFAR_MODE"
    if re.search(r"^#define\s+"+name+r"\s+", text, re.M):
        text = re.sub(r"^#define\s+"+name+r"\s+\d+", "#define "+name+" "+str(cfar_mode), text, flags=re.M)
    else:
        index = text.rfind("#endif")
        if index < 0:
            raise ValueError("Missing prj_config guard")
        text = text[:index]+"#define "+name+" "+str(cfar_mode)+"\n"+text[index:]
    config.write_text(text)
    for macro, value in [('CONFIG_MMW_PRESENCE_POINT_CLOUD_RANGE_DEC',range_dec),
                         ('CONFIG_MMW_PRESENCE_INTERVAL_NUM_LOG2',interval_log2),
                         ('CONFIG_MMW_PRESENCE_POINT_CLOUD_INTERVAL_DEC',frame_dec)]:
        pattern = r'^#define\s+'+macro+r'\s+[^\r\n]+'
        if re.search(pattern,text,re.M):
            text = re.sub(pattern,'#define '+macro+' '+str(value),text,flags=re.M)
        else:
            index=text.rfind('#endif')
            text=text[:index]+'#define '+macro+' '+str(value)+'\n'+text[index:]
    config.write_text(text)
    shutil.copyfile(pathlib.Path(__file__).with_name("citraverse_runtime.c"), source/"citraverse_runtime.c")
    workspace = source.parent / "cdk_6240_cpuf/presence.cdkws"
    workspace.write_text('<CDK_Workspace Name="CitraverseDevelopment" Database=""><Project Name="Posture_MRS6240_P2512" Path="project.cdkproj" Active="Yes"/><BuildMatrix><WorkspaceConfiguration Name="Debug" Selected="yes"><Environment/><Project Name="Posture_MRS6240_P2512" ConfigName="psdf"/></WorkspaceConfiguration></BuildMatrix></CDK_Workspace>')
    print(workspace)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdk", type=pathlib.Path, help="Disposable writable SDK copy, never the original download")
    parser.add_argument('--cfar-mode', type=int, choices=(0,1), default=1,
                        help='Experimental CFAR build variant: 0 single-side, 1 both-side (default)')
    parser.add_argument('--range-dec', type=int, choices=(1,2), default=2)
    parser.add_argument('--interval-log2', type=int, choices=(3,4), default=3)
    parser.add_argument('--frame-dec', type=int, choices=(2,4), default=4)
    args = parser.parse_args()
    install(args.sdk.resolve(), args.cfar_mode, args.range_dec, args.interval_log2, args.frame_dec)
