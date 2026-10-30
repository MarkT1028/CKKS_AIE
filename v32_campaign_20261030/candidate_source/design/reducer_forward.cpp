#include "ct_mac.hpp"
using namespace ctmac;
#ifndef PERF_COMPACT
#define PERF_COMPACT 0
#endif

namespace {
struct Products { product_t lane[4]; };
struct Residues { word_t lane[4]; };

// One process reconstructs, another reduces, a third accumulates/writes.
// Four independent memory banks support one 128-bit partial beat per cycle.
static void reconstruct(hls::stream<axis_t>& partials,
                        hls::stream<Products>& products,
                        unsigned n,unsigned l,unsigned k) {
#pragma HLS INLINE off
    product_t values[TILE];
#pragma HLS ARRAY_PARTITION variable=values cyclic factor=4 dim=1
    const unsigned frames=l*(n/TILE)*k*4;
    const unsigned beats_per_diagonal=TILE/4;
    const unsigned beats_per_frame=7*beats_per_diagonal;
    unsigned beat=0;
    // Last-diagonal forwarding: preserve frame/position order while removing
    // the separate TILE/4 output scan. Backpressure stalls this same pipeline.
    for(unsigned index=0;index<frames*beats_per_frame;++index) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=448 max=14680064
        const unsigned diagonal=beat/beats_per_diagonal;
        const unsigned j=(beat%beats_per_diagonal)*4;
        axis_t packed=partials.read();Products token;
        for(unsigned lane=0;lane<4;++lane) {
#pragma HLS UNROLL
            ap_uint<32> pp=packed.range(32*lane+31,32*lane);
            product_t previous=diagonal==0?product_t(0):values[j+lane];
            ap_uint<121> term=ap_uint<121>(pp)<<(15*diagonal);
            product_t value=product_t(ap_uint<121>(previous)+term);
            values[j+lane]=value;token.lane[lane]=value;
        }
        if(diagonal==6)products.write(token);
        beat=beat+1==beats_per_frame?0:beat+1;
    }
}

static void modular_reduce(hls::stream<Products>& products,
                           hls::stream<Residues>& residues,
                           const param_t cached[MAX_L],
                           unsigned n,unsigned l,unsigned k) {
#pragma HLS INLINE off
    for(unsigned t=0;t<l;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
        ap_uint<60> q=cached[t].range(59,0);
        reciprocal_t mu=cached[t].range(147,64);
        const unsigned tokens=(n/TILE)*k*4*(TILE/4);
        for(unsigned i=0;i<tokens;++i) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=64 max=131072
            Products in=products.read();Residues out;
            for(unsigned lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                out.lane[lane]=reduce(in.lane[lane],q,mu);
            }
            residues.write(out);
        }
    }
}

static void accumulate(hls::stream<Residues>& residues,word_t* outputs,
                       const param_t cached[MAX_L],
                       unsigned n,unsigned l,unsigned k) {
#pragma HLS INLINE off
    word_t sums[3][TILE];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums cyclic factor=4 dim=2
    for(unsigned t=0;t<l;++t) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
        ap_uint<60> q=cached[t].range(59,0);
        for(unsigned base=0;base<n;base+=TILE) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=128
            for(unsigned j=0;j<TILE;j+=4) {
#pragma HLS PIPELINE II=1
                for(unsigned component=0;component<3;++component) {
#pragma HLS UNROLL
                    for(unsigned lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                        sums[component][j+lane]=0;
                    }
                }
            }
            for(unsigned pair=0;pair<k;++pair) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
                for(unsigned product=0;product<4;++product) {
                    unsigned component=product==0?0:product==3?2:1;
                    for(unsigned j=0;j<TILE;j+=4) {
#pragma HLS PIPELINE II=1
                        Residues token=residues.read();
                        for(unsigned lane=0;lane<4;++lane) {
#pragma HLS UNROLL
                            sums[component][j+lane]=add_mod(sums[component][j+lane],token.lane[lane],q);
                        }
                    }
                }
            }
            for(unsigned j=0;j<TILE;++j)
                for(unsigned component=0;component<3;++component) {
#pragma HLS PIPELINE II=1
                    outputs[(t*n+base+j)*3+component]=sums[component][j];
                }
        }
    }
}

static void pipeline(hls::stream<axis_t>& partials,word_t* outputs,
                     const param_t cached[MAX_L],
                     unsigned n,unsigned l,unsigned k) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<Products> products("products");
    hls::stream<Residues> residues("residues");
#pragma HLS STREAM variable=products depth=32
#pragma HLS STREAM variable=residues depth=32
    reconstruct(partials,products,n,l,k);
    modular_reduce(products,residues,cached,n,l,k);
    accumulate(residues,outputs,cached,n,l,k);
}
}

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
    int status=dimensions(n,l,k);if(status!=OK)return status;
    param_t cached[MAX_L];
    for(unsigned t=0;t<l;++t) {
        cached[t]=params[t];
        if(!valid_parameter(cached[t]))return BAD_PARAMETER;
    }
    pipeline(partials,outputs,cached,n,l,k);
    return OK;
}
