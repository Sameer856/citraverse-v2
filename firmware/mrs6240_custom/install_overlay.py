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

def install(sdk):
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
        text = re.sub(r"^#define\s+"+name+r"\s+\d+", "#define "+name+" 1", text, flags=re.M)
    else:
        index = text.rfind("#endif")
        if index < 0:
            raise ValueError("Missing prj_config guard")
        text = text[:index]+"#define "+name+" 1\n"+text[index:]
    config.write_text(text)
    shutil.copyfile(pathlib.Path(__file__).with_name("citraverse_runtime.c"), source/"citraverse_runtime.c")
    workspace = source.parent / "cdk_6240_cpuf/presence.cdkws"
    workspace.write_text('<CDK_Workspace Name="CitraverseDevelopment" Database=""><Project Name="Posture_MRS6240_P2512" Path="project.cdkproj" Active="Yes"/><BuildMatrix><WorkspaceConfiguration Name="Debug" Selected="yes"><Environment/><Project Name="Posture_MRS6240_P2512" ConfigName="psdf"/></WorkspaceConfiguration></BuildMatrix></CDK_Workspace>')
    print(workspace)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdk", type=pathlib.Path, help="Disposable writable SDK copy, never the original download")
    install(parser.parse_args().sdk.resolve())
