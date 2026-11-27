"""Exercise production jitter-buffer priming, short turns and timer wrap."""
from pathlib import Path
import subprocess,tempfile

def test_speaker_buffer():
    source=r'''
#include <assert.h>
#include "speaker_buffer.h"
int main(void){
 speaker_buffer_t b={0};
 assert(!speaker_buffer_ready(&b,0,1000));
 assert(!speaker_buffer_ready(&b,6,1000));
 assert(!speaker_buffer_ready(&b,6,1100));
 assert(speaker_buffer_ready(&b,12,1120));
 assert(speaker_buffer_ready(&b,1,1200));
 assert(!speaker_buffer_ready(&b,0,1220));
 assert(!speaker_buffer_ready(&b,1,2000));
 assert(!speaker_buffer_ready(&b,1,2239));
 assert(speaker_buffer_ready(&b,1,2240));
 b=(speaker_buffer_t){0};
 assert(!speaker_buffer_ready(&b,1,0xfffffff0u));
 assert(speaker_buffer_ready(&b,1,224));
 return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory);(p/'buffer.c').write_text(source)
        subprocess.run(['clang','-fsanitize=address,undefined','-I',str(Path(__file__).parents[1]/'main'),str(p/'buffer.c'),'-o',str(p/'buffer')],check=True)
        subprocess.run([str(p/'buffer')],check=True)
