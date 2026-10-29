from pathlib import Path
R=Path(__file__).resolve().parent
def main():
    source=(R/'reference/design/reducer_pipeline.cpp').read_text()
    begin=source.index('    const unsigned frames=l*(n/TILE)*k*4;');end=source.index('\n}\n\nstatic void modular_reduce',begin)
    body='''    const unsigned frames=l*(n/TILE)*k*4;
    const unsigned beats_per_diagonal=TILE/4;
    const unsigned beats_per_frame=7*beats_per_diagonal;
    unsigned beat=0;
    // Last-diagonal forwarding: preserve frame/position order while removing
    // the separate TILE/4 output scan. Backpressure stalls this same pipeline.
    for(unsigned index=0;index<frames*beats_per_frame;++index) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=448 max=14680064
        const unsigned diagonal=beat/beats_per_diagonal;
        const unsigned j=(beat%beats_per_diagonal)*4;
        axis_t packed=partials.read();Products token;
        for(unsigned lane=0;lane<4;++lane) {
#pragma HLS UNROLL
            ap_uint<32> pp=packed.range(32*lane+31,32*lane);
            product_t previous=diagonal==0?product_t(0):values[j+lane];
            ap_uint<121> term=ap_uint<121>(pp)<<(15*diagonal);
            product_t value=product_t(ap_uint<121>(previous)+term);
            values[j+lane]=value;token.lane[lane]=value;
        }
        if(diagonal==6)products.write(token);
        beat=beat+1==beats_per_frame?0:beat+1;
    }'''
    (R/'design/reducer_forward.cpp').write_text(source[:begin]+body+source[end:])
    # All branches below are template constants, and each diagonal keeps its
    # original two 32-position vectors and unsigned output order.
    kernel='''#include <adf.h>
#include <aie_api/aie.hpp>
template<unsigned D> static inline void diagonal(const int16* a,const int16* b,uint32* out) {
    for(unsigned j=0;j<64;j+=32) chess_prepare_for_pipelining chess_loop_range(2,2) {
        aie::accum<acc64,32> s=aie::zeros<acc64,32>();
'''
    for r in range(4):
        kernel+=f'''        if(D>={r} && D-{r}<4) {{
            auto av=aie::load_v<32>(a+{r}*64+j);
            auto bv=aie::load_v<32>(b+(D-{r})*64+j);
            s=aie::mac(s,av,bv);
        }}
'''
    kernel+='''        aie::store_v(out+D*64+j,s.to_vector<uint32>(0));
    }
}
void limb_diag(adf::input_buffer<int16>& left,adf::input_buffer<int16>& right,adf::output_buffer<uint32>& output) {
    const int16* a=left.data();const int16* b=right.data();uint32* out=output.data();
'''
    kernel+=''.join(f'    diagonal<{d}>(a,b,out);\n' for d in range(7))+'}\n'
    (R/'aie/limb_diag.cpp').write_text(kernel)
    print('CANDIDATE_SOURCES_CREATED')
if __name__=='__main__':main()
