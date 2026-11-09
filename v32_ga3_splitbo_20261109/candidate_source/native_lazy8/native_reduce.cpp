#include "ct_mac.hpp"
using namespace ctmac;
namespace {
// For canonical q<2^60 and k<=16:
// c0,c2 <16*q^2 <2^124; c1<32*q^2<2^125. 128 bits are exact.
// mu=floor(2^128/q), x<2^128 => floor(x*mu/2^128) is at most
// one below floor(x/q). A single conditional subtraction is sufficient.
static word_t reduce_sum(ap_uint<128> sum,ap_uint<60> q,reciprocal_t mu){
#pragma HLS INLINE
 ap_uint<212> scaled=ap_uint<212>(sum)*ap_uint<212>(mu);
 ap_uint<84> quotient=scaled.range(211,128);
 ap_uint<144> times_q=ap_uint<144>(quotient)*ap_uint<144>(q);
 ap_uint<145> remainder=ap_uint<145>(sum)-ap_uint<145>(times_q);
 if(remainder>=q)remainder-=q;
 return word_t(remainder);
}
static void accumulate(hls::stream<products_t>& products,word_t* outputs,
 const param_t cached[MAX_L],unsigned n,unsigned l,unsigned k){
#pragma HLS INLINE off
 ap_uint<128> sums[3][TILE];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums cyclic factor=8 dim=2
 for(unsigned t=0;t<l;++t){
  const ap_uint<60> q=cached[t].range(59,0);const reciprocal_t mu=cached[t].range(147,64);
  for(unsigned base=0;base<n;base+=TILE){
   for(unsigned j=0;j<TILE;j+=8){
#pragma HLS PIPELINE II=1
    for(unsigned c=0;c<3;++c){
#pragma HLS UNROLL
     for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
      sums[c][j+lane]=0;
     }
    }
   }
   for(unsigned pair=0;pair<k;++pair){
    for(unsigned product=0;product<4;++product){
     const unsigned component=product==0?0:product==3?2:1;
     for(unsigned j=0;j<TILE;j+=8){
#pragma HLS PIPELINE II=1
      products_t token=products.read();
      for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
       sums[component][j+lane]+=ap_uint<128>(token.range(120*lane+119,120*lane));
      }
     }
    }
   }
   for(unsigned j=0;j<TILE;++j)for(unsigned c=0;c<3;++c){
#pragma HLS PIPELINE II=1
    outputs[(t*n+base+j)*3+c]=reduce_sum(sums[c][j],q,mu);
   }
  }
 }
}
}
extern "C" int ct_reduce_accum(hls::stream<products_t>& products,word_t* outputs,
 const param_t* params,unsigned n,unsigned l,unsigned k){
#pragma HLS INTERFACE axis port=products
#pragma HLS INTERFACE m_axi port=outputs offset=slave bundle=gmem0 depth=393216 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem1 depth=16
#pragma HLS INTERFACE s_axilite port=outputs bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 int status=dimensions(n,l,k);if(status!=OK)return status;param_t cached[MAX_L];
 for(unsigned t=0;t<l;++t){cached[t]=params[t];if(!valid_parameter(cached[t]))return BAD_PARAMETER;}
 accumulate(products,outputs,cached,n,l,k);return OK;
}
