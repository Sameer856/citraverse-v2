"""Check real speaker gain and signed sample boundaries under sanitizers."""
import subprocess, tempfile
from pathlib import Path

def test_speaker_gain():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory); source=root/"gain.c"; binary=root/"gain"
        source.write_text('#include <assert.h>\n#include <stdint.h>\n#include "speaker_gain.h"\nint main(void){\n uint32_t g=256;\n assert(speaker_next_gain_q8(g,0)==256);\n assert(speaker_next_gain_q8(g,63)==256);\n for(int i=0;i<100;i++)g=speaker_next_gain_q8(g,2000);\n assert(g==2048);\n assert(speaker_sample_i2s(2000,g)==16000*65536);\n g=speaker_next_gain_q8(g,32768);\n assert(g<=256);\n for(int s=-32768;s<=32767;s++){\n  int32_t out=speaker_sample_i2s((int16_t)s,g);\n  assert(out/65536>=-32768 && out/65536<=32767);\n }\n assert(speaker_sample_i2s(-32768,256)==INT32_MIN);\n assert(speaker_sample_i2s(32767,256)==2147418112);\n return 0;\n}\n')
        subprocess.run(["clang","-fsanitize=address,undefined","-I",str(Path(__file__).parents[1]/"main"),str(source),"-o",str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
