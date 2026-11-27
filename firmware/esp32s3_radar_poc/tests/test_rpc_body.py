"""Exercise the real body reader when headers already buffered the whole reply."""
from pathlib import Path
import subprocess, tempfile

def test_buffered_and_partial_rpc_body():
    text=(Path(__file__).parents[1]/'main/radar_cloud.c').read_text()
    function=text[text.index('static int read_rpc_body('):text.index('static void execute(')]
    fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
typedef struct {const char *body;int remaining;int chunk;bool complete;int error;} state;
typedef state *esp_http_client_handle_t;
static int esp_http_client_read(state *s,char *out,int cap){
 if(s->error)return -1;
 int n=s->remaining;if(n>cap)n=cap;if(n>s->chunk)n=s->chunk;
 memcpy(out,s->body,n);s->body+=n;s->remaining-=n;return n;
}
static bool esp_http_client_is_complete_data_received(state *s){return s->complete;}
'''
    cases=r'''
int main(void){
 uint8_t out[64]={0};
 state buffered={"call-token-json",15,64,true,0};
 assert(read_rpc_body(&buffered,out,64)==15);assert(!memcmp(out,"call-token-json",15));
 state chunks={"abcdef",6,2,true,0};assert(read_rpc_body(&chunks,out,64)==6);assert(!memcmp(out,"abcdef",6));
 state truncated={"abc",3,2,false,0};assert(read_rpc_body(&truncated,out,64)==-1);
 state failed={"",0,64,false,1};assert(read_rpc_body(&failed,out,64)==-1);
 state overflow={"abcd",4,4,true,0};assert(read_rpc_body(&overflow,out,4)==-1);
 return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory);(p/'body.c').write_text(fixture+function+cases)
        subprocess.run(['clang','-fsanitize=address,undefined',str(p/'body.c'),'-o',str(p/'body')],check=True)
        subprocess.run([str(p/'body')],check=True)
