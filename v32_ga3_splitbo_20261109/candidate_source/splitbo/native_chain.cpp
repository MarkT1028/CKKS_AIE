#include "ct_mac.hpp"
using namespace ctmac;
extern "C" int native_split_chain(const input_t* weights,const input_t* baby,word_t* outputs,const param_t* params,unsigned n,unsigned l,unsigned k,unsigned lane){
#pragma HLS INTERFACE m_axi port=weights offset=slave bundle=gmem0 depth=16384 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=baby offset=slave bundle=gmem1 depth=16384 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=outputs offset=slave bundle=gmem2 depth=6146
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem3 depth=16
#pragma HLS INTERFACE s_axilite port=weights bundle=control
#pragma HLS INTERFACE s_axilite port=baby bundle=control
#pragma HLS INTERFACE s_axilite port=outputs bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=lane bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
#pragma HLS DATAFLOW
 hls::stream<products_t> products("split_products");
#pragma HLS STREAM variable=products depth=32
 int a=ct_reader(weights,baby,products,n,l,k,lane);
 int b=ct_reduce_accum(products,outputs,params,n,l,k);
 return a|b;
}
