#include "ct_mac.hpp"
using namespace ctmac;
extern "C" int ct_limb_diag(hls::stream<axis_t>&,hls::stream<axis_t>&,hls::stream<axis_t>&,unsigned,unsigned,unsigned);
// Verification-only fused top. Production uses the three separately linked CUs.
extern "C" int pure_pl_chain(const word_t* input,word_t* output,const param_t* params,unsigned n,unsigned l,unsigned k){
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem0 depth=24576
#pragma HLS INTERFACE m_axi port=output offset=slave bundle=gmem1 depth=1152
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem2 depth=16
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=output bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS DATAFLOW
 hls::stream<axis_t> a("a"),b("b"),p("p");
#pragma HLS STREAM variable=a depth=64
#pragma HLS STREAM variable=b depth=64
#pragma HLS STREAM variable=p depth=64
 int r0=ct_reader(input,a,b,n,l,k);int r1=ct_limb_diag(a,b,p,n,l,k);int r2=ct_reduce_accum(p,output,params,n,l,k);
 return r0?r0:r1?r1:r2;
}
