#include "ct_mac.hpp"
#include <hls_streamofblocks.h>
using namespace ctmac;
namespace {
typedef ap_uint<240> Window[TILE];
static void load(const input_t* inputs,hls::stream_of_blocks<Window,2>& windows,unsigned n,unsigned l,unsigned k){
#pragma HLS INLINE off
 for(unsigned t=0;t<l;++t)for(unsigned base=0;base<n;base+=TILE)for(unsigned pair=0;pair<k;++pair){
  hls::write_lock<Window> block(windows);
  const unsigned begin=((pair*l+t)*n+base)/2;
  for(unsigned j=0;j<TILE;j+=2){
#pragma HLS PIPELINE II=1
   const input_t wide=inputs[begin+j/2];
   for(unsigned c=0;c<2;++c){
#pragma HLS UNROLL
    ap_uint<240> packed=0;
    for(unsigned v=0;v<4;++v){
#pragma HLS UNROLL
     packed.range(60*v+59,60*v)=wide.range(256*c+64*v+59,256*c+64*v);
    }
    block[j+c]=packed;
   }
  }
 }
}
static void multiply(hls::stream_of_blocks<Window,2>& windows,hls::stream<products_t>& products,unsigned frames){
#pragma HLS INLINE off
 for(unsigned frame=0;frame<frames;++frame){
  hls::read_lock<Window> block(windows);
  for(unsigned product=0;product<4;++product)for(unsigned j=0;j<TILE;j+=4){
#pragma HLS PIPELINE II=1
   products_t packed=0;
   for(unsigned lane=0;lane<4;++lane){
#pragma HLS UNROLL
    const ap_uint<240> word=block[j+lane];
    ap_uint<60> a0=word.range(59,0),a1=word.range(119,60),b0=word.range(179,120),b1=word.range(239,180);
    ap_uint<60> a=product<2?a0:a1,b=(product&1)?b1:b0;
    product_t value=a*b;packed.range(120*lane+119,120*lane)=value;
   }
   products.write(packed);
  }
 }
}
static void pipeline(const input_t* input,hls::stream<products_t>& products,unsigned n,unsigned l,unsigned k){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 hls::stream_of_blocks<Window,2> windows;
#pragma HLS ARRAY_PARTITION variable=windows cyclic factor=4 dim=1
#pragma HLS BIND_STORAGE variable=windows type=RAM_2P impl=LUTRAM
 load(input,windows,n,l,k);multiply(windows,products,(n/TILE)*l*k);
}
}
extern "C" int ct_reader(const input_t* inputs,hls::stream<products_t>& products,unsigned n,unsigned l,unsigned k){
#pragma HLS INTERFACE m_axi port=inputs offset=slave bundle=gmem depth=1048576 max_read_burst_length=64
#pragma HLS INTERFACE axis port=products
#pragma HLS INTERFACE s_axilite port=inputs bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 int status=dimensions(n,l,k);if(status!=OK)return status;
 pipeline(inputs,products,n,l,k);return OK;
}
