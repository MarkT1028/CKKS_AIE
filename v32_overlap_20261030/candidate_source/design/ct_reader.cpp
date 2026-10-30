#include "ct_mac.hpp"
using namespace ctmac;
extern "C" int ct_reader(const word_t* inputs,
    hls::stream<axis_t>& left,hls::stream<axis_t>& right,
    unsigned n,unsigned l,unsigned k) {
#pragma HLS INTERFACE m_axi port=inputs offset=slave bundle=gmem depth=8388608 max_read_burst_length=64
#pragma HLS INTERFACE axis port=left
#pragma HLS INTERFACE axis port=right
#pragma HLS INTERFACE s_axilite port=inputs bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    int status=dimensions(n,l,k);
    if(status!=OK) return status;
    word_t tile[4][TILE];
#pragma HLS ARRAY_PARTITION variable=tile complete dim=1
    for(unsigned t=0;t<l;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
        for(unsigned base=0;base<n;base+=TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=128
            for(unsigned pair=0;pair<k;++pair) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
                for(unsigned j=0;j<TILE;++j) {
                    for(unsigned c=0;c<4;++c) {
#pragma HLS PIPELINE II=1
                        unsigned idx=(((pair*l+t)*n+base+j)*4+c);
                        tile[c][j]=inputs[idx];
                    }
                }
                // Order: 00,01,10,11; two 128-bit streams, eight int16 lanes each.
                for(unsigned product=0;product<4;++product) {
                    unsigned ac=product/2,bc=2+product%2;
                    for(unsigned limb=0;limb<4;++limb) {
                        for(unsigned j=0;j<TILE;j+=8) {
                            axis_t a=0,b=0;
                            for(unsigned lane=0;lane<8;++lane) {
                                ap_uint<16> av=(tile[ac][j+lane]>>(15*limb))&32767;
                                ap_uint<16> bv=(tile[bc][j+lane]>>(15*limb))&32767;
                                a.range(16*lane+15,16*lane)=av;
                                b.range(16*lane+15,16*lane)=bv;
                            }
                            left.write(a); right.write(b);
                        }
                    }
                }
            }
        }
    }
    return OK;
}
