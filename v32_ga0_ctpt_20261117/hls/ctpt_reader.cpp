#include "ct_mac.hpp"
#include <hls_streamofblocks.h>
using namespace ctmac;
namespace {
typedef ap_uint<180> Window[TILE];
// A is [term][tower][full coefficient][two ciphertext components].
// B carries one 64-bit plaintext residue per coefficient.
static void load(const input_t* weights, const input_t* baby,
                 hls::stream_of_blocks<Window,2>& windows,
                 unsigned n, unsigned l, unsigned k, unsigned lane) {
#pragma HLS INLINE off
 for (unsigned t=0;t<l;++t) for (unsigned base=0;base<n;base+=TILE)
  for (unsigned pair=0;pair<k;++pair) {
   hls::write_lock<Window> block(windows);
   const unsigned start=(pair*l+t)*(2*n)+lane*n+base;
   for (unsigned j=0;j<TILE;j+=8) {
#pragma HLS PIPELINE II=2
    const input_t b=baby[(start+j)/8];
    const input_t a_low=weights[(start+j)/4];
    const input_t a_high=weights[(start+j)/4+1];
    for (unsigned c=0;c<8;++c) {
#pragma HLS UNROLL
     const input_t a=c<4?a_low:a_high;
     ap_uint<180> packed=0;
     packed.range(59,0)=a.range(128*(c%4)+59,128*(c%4));
     packed.range(119,60)=a.range(128*(c%4)+123,128*(c%4)+64);
     packed.range(179,120)=b.range(64*c+59,64*c);
     block[j+c]=packed;
    }
   }
  }
}
static void multiply(hls::stream_of_blocks<Window,2>& windows,hls::stream<products_t>& products,unsigned frames){
#pragma HLS INLINE off
 for(unsigned frame=0;frame<frames;++frame){
  hls::read_lock<Window> block(windows);
  for(unsigned product=0;product<2;++product)for(unsigned j=0;j<TILE;j+=8){
#pragma HLS PIPELINE II=1
   products_t packed=0;
   for(unsigned c=0;c<8;++c){
#pragma HLS UNROLL
    const ap_uint<180> word=block[j+c];
    ap_uint<60> a0=word.range(59,0),a1=word.range(119,60),m=word.range(179,120);
    product_t value=(product==0?a0:a1)*m;
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
#pragma HLS INTERFACE m_axi port=baby offset=slave bundle=gmem_baby depth=262144 max_read_burst_length=64
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
