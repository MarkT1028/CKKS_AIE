#include "ct_mac.hpp"
#include <hls_streamofblocks.h>
using namespace ctmac;
namespace {
// Each word stores all4 limbs of A and B for one coefficient. A 2-block
// memory channel avoids shifting a7680-bit aggregate through a wide FIFO.
typedef ap_uint<120> Window[TILE];
static void load(hls::stream<axis_t>& left,hls::stream<axis_t>& right,
                 hls::stream_of_blocks<Window,2>& windows,unsigned frames){
#pragma HLS INLINE off
 for(unsigned frame=0;frame<frames;++frame){
#pragma HLS LOOP_TRIPCOUNT min=4 max=131072
  hls::write_lock<Window> block(windows);
  for(unsigned limb=0;limb<4;++limb)for(unsigned j=0;j<TILE;j+=8){
#pragma HLS PIPELINE II=1
   axis_t a=left.read(),b=right.read();
   for(unsigned lane=0;lane<8;++lane){
#pragma HLS UNROLL
    ap_uint<120> packed=limb==0?ap_uint<120>(0):block[j+lane];
    packed.range(15*limb+14,15*limb)=a.range(16*lane+14,16*lane);
    packed.range(60+15*limb+14,60+15*limb)=b.range(16*lane+14,16*lane);
    block[j+lane]=packed;
   }
  }
 }
}
static void multiply(hls::stream_of_blocks<Window,2>& windows,hls::stream<axis_t>& output,unsigned frames){
#pragma HLS INLINE off
 for(unsigned frame=0;frame<frames;++frame){
#pragma HLS LOOP_TRIPCOUNT min=4 max=131072
  hls::read_lock<Window> block(windows);
  // One shared4-lane datapath for the7 diagonals, rather than7 separately
  // instantiated multiply pipelines. Preserve the original exact32-bit sums.
  for(unsigned d=0;d<7;++d)for(unsigned j=0;j<TILE;j+=4){
#pragma HLS PIPELINE II=1
   axis_t packed=0;
   for(unsigned lane=0;lane<4;++lane){
#pragma HLS UNROLL
    const ap_uint<120> word=block[j+lane];ap_uint<32> sum=0;
    for(unsigned r=0;r<4;++r){
#pragma HLS UNROLL
     ap_uint<15> a=word.range(15*r+14,15*r),b=0;
     if(d>=r&&d-r<4)b=word.range(60+15*(d-r)+14,60+15*(d-r));
     const ap_uint<30> product=a*b;sum+=ap_uint<32>(product);
    }
    packed.range(32*lane+31,32*lane)=sum;
   }
   output.write(packed);
  }
 }
}
static void pipeline(hls::stream<axis_t>& left,hls::stream<axis_t>& right,hls::stream<axis_t>& output,unsigned frames){
#pragma HLS INLINE off
#pragma HLS DATAFLOW
 hls::stream_of_blocks<Window,2> windows;
#pragma HLS ARRAY_PARTITION variable=windows cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=windows type=RAM_2P impl=LUTRAM
 load(left,right,windows,frames);multiply(windows,output,frames);
}
}
extern "C" int ct_limb_diag(hls::stream<axis_t>& left,hls::stream<axis_t>& right,hls::stream<axis_t>& partials,unsigned n,unsigned l,unsigned k){
#pragma HLS INTERFACE axis port=left
#pragma HLS INTERFACE axis port=right
#pragma HLS INTERFACE axis port=partials
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
 int status=dimensions(n,l,k);if(status!=OK)return status;
 pipeline(left,right,partials,(n/TILE)*l*k*4);return OK;
}
