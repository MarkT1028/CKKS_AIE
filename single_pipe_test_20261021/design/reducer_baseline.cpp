#include "ct_mac.hpp"
using namespace ctmac;
extern "C" int ct_reduce_accum(hls::stream<axis_t>& partials,
    word_t* outputs,const param_t* params,unsigned n,unsigned l,unsigned k) {
#pragma HLS INTERFACE axis port=partials
#pragma HLS INTERFACE m_axi port=outputs offset=slave bundle=gmem0 depth=393216 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem1 depth=16
#pragma HLS INTERFACE s_axilite port=outputs bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    int status=dimensions(n,l,k);
    if(status!=OK) return status;
    // Validate all parameters before consuming a stream or writing output.
    param_t cached[MAX_L];
    for(unsigned t=0;t<l;++t) {
        cached[t]=params[t];
        if(!valid_parameter(cached[t])) return BAD_PARAMETER;
    }
    word_t sums[3][TILE];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
    product_t products[TILE];
    // Four incoming lanes access distinct banks in the same cycle.
#pragma HLS ARRAY_PARTITION variable=products cyclic factor=4 dim=1
    for(unsigned t=0;t<l;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
        ap_uint<60> q=cached[t].range(59,0);
        reciprocal_t mu=cached[t].range(144,64);
        for(unsigned base=0;base<n;base+=TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=128
            for(unsigned j=0;j<TILE;++j)
                for(unsigned c=0;c<3;++c) sums[c][j]=0;
            for(unsigned pair=0;pair<k;++pair) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
                for(unsigned product=0;product<4;++product) {
                    for(unsigned j=0;j<TILE;++j) products[j]=0;
                    for(unsigned r=0;r<4;++r) {
                        for(unsigned s=0;s<4;++s) {
                            for(unsigned j=0;j<TILE;j+=4) {
                                axis_t packed=partials.read();
                                for(unsigned lane=0;lane<4;++lane) {
                                    ap_uint<32> pp=packed.range(32*lane+31,32*lane);
                                    // Valid AIE products are <2^30. Widen BEFORE shifting.
                                    ap_uint<121> term=ap_uint<121>(pp)<<(15*(r+s));
                                    ap_uint<121> total=ap_uint<121>(products[j+lane])+term;
                                    products[j+lane]=product_t(total);
                                }
                            }
                        }
                    }
                    unsigned component=product==0?0:(product==3?2:1);
                    for(unsigned j=0;j<TILE;++j) {
                        word_t reduced=reduce(products[j],q,mu);
                        sums[component][j]=add_mod(sums[component][j],reduced,q);
                    }
                }
            }
            for(unsigned j=0;j<TILE;++j)
                for(unsigned c=0;c<3;++c) {
#pragma HLS PIPELINE II=1
                    outputs[((t*n+base+j)*3+c)]=sums[c][j];
                }
        }
    }
    return OK;
}
