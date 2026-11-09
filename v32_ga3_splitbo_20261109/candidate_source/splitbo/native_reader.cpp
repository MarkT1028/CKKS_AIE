#include "ct_mac.hpp"
#include <hls_streamofblocks.h>
using namespace ctmac;
namespace {
typedef ap_uint<240> Window[TILE];
// Each input retains canonical [pair][tower][full coefficient][component] order.
// Both lanes share read-only BOs; lane selects a disjoint half of coefficients.
static void load(const input_t* weights,const input_t* baby,hls::stream_of_blocks<Window,2>& windows,unsigned n,unsigned l,unsigned k,unsigned lane){
#pragma HLS INLINE off
 for(unsigned t=0;t<l;++t)for(unsigned base=0;base<n;base+=TILE)for(unsigned pair=0;pair<k;++pair){
  hls::write_lock<Window> block(windows);
  const unsigned begin=((pair*l+t)*(2*n)+lane*n+base)/4;
  for(unsigned j=0;j<TILE;j+=4){
#pragma HLS PIPELINE II=1
   const input_t a=weights[begin+j/4],b=baby[begin+j/4];
   for(unsigned c=0;c<4;++c){
#pragma HLS UNROLL
    ap_uint<240> packed=0;
    packed.range(59,0)=a.range(128*c+59,128*c);
    packed.range(119,60)=a.range(128*c+123,128*c+64);
    packed.range(179,120)=b.range(128*c+59,128*c);
    packed.range(239,180)=b.range(128*c+123,128*c+64);
    block[j+c]=packed;
   }
  }
 }
}
static void multiply(hls::stream_of_blocks<Window,2>& windows,hls::stream<products_t>& products,unsigned frames){
#pragma HLS INLINE off
 for(unsigned frame=0;frame<frames;++frame){
  hls::read_lock<Window> block(windows);
  for(unsigned product=0;product<4;++product)for(unsigned j=0;j<TILE;j+=8){
#pragma HLS PIPELINE II=1
   products_t packed=0;
   for(unsigned c=0;c<8;++c){
#pragma HLS UNROLL
    const ap_uint<240> word=block[j+c];
    ap_uint<60> a0=word.range(59,0),a1=word.range(119,60),b0=word.range(179,120),b1=word.range(239,180);
    product_t value=(product<2?a0:a1)*((product&1)?b1:b0);
    packed.range(120*c+119,120*c)=value;
   }
   products.write(packed);
  }
 }
}
static void pipeline(const input_t* weights,const input_t* baby,hls::stream<products_t>& products,unsigned n,unsigned l,unsigned k,unsigned lane){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 hls::stream_of_blocks<Window,2> windows;
#pragma HLS ARRAY_PARTITION variable=windows cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=windows type=RAM_2P impl=LUTRAM
 load(weights,baby,windows,n,l,k,lane);multiply(windows,products,(n/TILE)*l*k);
}
}
extern "C" int ct_reader(const input_t* weights,const input_t* baby,hls::stream<products_t>& products,unsigned n,unsigned l,unsigned k,unsigned lane){
#pragma HLS INTERFACE m_axi port=weights offset=slave bundle=gmem_weights depth=524288 max_read_burst_length=64
#pragma HLS INTERFACE m_axi port=baby offset=slave bundle=gmem_baby depth=524288 max_read_burst_length=64
#pragma HLS INTERFACE axis port=products
#pragma HLS INTERFACE s_axilite port=weights bundle=control
#pragma HLS INTERFACE s_axilite port=baby bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=lane bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 int status=dimensions(n,l,k);if(status!=OK)return status;
 if(n>MAX_N/2)return BAD_N;if(lane>1)return 5;
 pipeline(weights,baby,products,n,l,k,lane);return OK;
}
