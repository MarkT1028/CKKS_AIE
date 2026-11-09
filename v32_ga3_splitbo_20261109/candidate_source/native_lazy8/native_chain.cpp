#include "ct_mac.hpp"
using namespace ctmac;
extern "C" int native_pl_chain(const input_t* inputs,word_t* outputs,const param_t* params,unsigned n,unsigned l,unsigned k){
#pragma HLS INTERFACE m_axi port=inputs offset=slave bundle=gmem0 depth=3072 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=outputs offset=slave bundle=gmem1 depth=1154
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem2 depth=16
#pragma HLS INTERFACE s_axilite port=inputs bundle=control
#pragma HLS INTERFACE s_axilite port=outputs bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS DATAFLOW
 hls::stream<products_t> products("native_products");
#pragma HLS STREAM variable=products depth=32
 int a=ct_reader(inputs,products,n,l,k);
 int b=ct_reduce_accum(products,outputs,params,n,l,k);
 return a|b;
}
