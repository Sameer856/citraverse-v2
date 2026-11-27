"""Compile the actual radar command validator and exercise unsafe/boundary inputs."""
from pathlib import Path
import subprocess
import tempfile


def test_command_validation():
    source = (Path(__file__).parents[1] / 'main/radar_control.c').read_text()
    declaration = source[source.index('typedef struct {\n    int frequency'):source.index('static const tuning_profile_t defaults=')]
    valid = source[source.index('static bool profile_valid('):source.index('static void tuning_load(')]
    parser = source[source.index('static bool parse_command('):source.index('static void tuning_worker(')]
    test = r'''
int main(void) {
 const tuning_profile_t base={58000,6400,25,3200,200,50,1,80,-1,0};tuning_profile_t p=base;
#define REJECT(command) do {p=base;assert(!parse_command(command,&p));} while(0)
 assert(parse_command("mmwc cfar 1 80",&p)&&p.cfar_value==80&&p.cfar_method==-1);
 assert(parse_command("mmwc cfar 0 24 0",&p)&&p.static_rm==0&&p.cfar_method==0);
 assert(parse_command("mmwc range 6400 25",&p));
 REJECT("mmwc cfar 0 120 0");
 REJECT("mmwc cfar 1 80\rmmwc start");
 REJECT("mmwc cfar 1 80;mmwc stop");
 REJECT("mmwc freq 9999999999999999999999999999");
 REJECT("mmwc frame 50 1");
 REJECT("mmwc range -1 25");
 REJECT("mmwc noise est");
 REJECT("mmwc comtype 0");
 REJECT("mmwc coord polar");
 REJECT("mmwc cfar 1");
 REJECT("mmwc cfar 1 80 0 4");
 REJECT("mmwc freq 58000foo");
 return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        c = Path(directory) / 'validate.c'
        c.write_text('#include <stdbool.h>\n#include <string.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <limits.h>\n#include <errno.h>\n#include <assert.h>\n'+declaration+valid+parser+test)
        binary = Path(directory) / 'validate'
        subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',str(c),'-o',str(binary)],check=True)
        subprocess.run([str(binary)],check=True)
