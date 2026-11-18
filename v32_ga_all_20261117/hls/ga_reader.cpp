#include "ct_mac.hpp"
#include <hls_streamofblocks.h>

using namespace ctmac;

namespace {
using Window = ap_uint<240>[TILE];

void load(const input_t* weights, const input_t* baby,
          hls::stream_of_blocks<Window, 2>& windows,
          unsigned n, unsigned l, unsigned k, unsigned lane, bool plaintext) {
#pragma HLS INLINE off
    for (unsigned t = 0; t < l; ++t)
        for (unsigned base = 0; base < n; base += TILE)
            for (unsigned pair = 0; pair < k; ++pair) {
                hls::write_lock<Window> block(windows);
                const unsigned start = (pair*l + t)*(2*n) + lane*n + base;
                for (unsigned j = 0; j < TILE; j += 8) {
#pragma HLS PIPELINE II=2
                    const unsigned a_index = (start + j)/4;
                    const input_t a_low = weights[a_index];
                    const input_t a_high = weights[a_index + 1];
                    const input_t b_low = baby[plaintext ? a_index/2 : a_index];
                    input_t b_high = 0;
                    if (!plaintext) b_high = baby[a_index + 1];
                    for (unsigned c = 0; c < 8; ++c) {
#pragma HLS UNROLL
                        const input_t a = c < 4 ? a_low : a_high;
                        const input_t b = c < 4 ? b_low : b_high;
                        const unsigned offset = 128*(c%4);
                        ap_uint<240> entry = 0;
                        entry.range(59, 0) = a.range(offset + 59, offset);
                        entry.range(119, 60) = a.range(offset + 123, offset + 64);
                        if (plaintext) {
                            entry.range(179, 120) = b_low.range(64*c + 59, 64*c);
                        } else {
                            entry.range(179, 120) = b.range(offset + 59, offset);
                            entry.range(239, 180) = b.range(offset + 123, offset + 64);
                        }
                        block[j + c] = entry;
                    }
                }
            }
}

void multiply(hls::stream_of_blocks<Window, 2>& windows, hls::stream<products_t>& products,
              unsigned frames, bool plaintext) {
#pragma HLS INLINE off
    const unsigned passes = plaintext ? 2 : 3;
    for (unsigned f = 0; f < frames; ++f) {
        hls::read_lock<Window> block(windows);
        for (unsigned pass = 0; pass < passes; ++pass)
            for (unsigned j = 0; j < TILE; j += 8) {
#pragma HLS PIPELINE II=1
                products_t token = 0;
                for (unsigned c = 0; c < 8; ++c) {
#pragma HLS UNROLL
                    const ap_uint<240> entry = block[j + c];
                    const ap_uint<60> a0 = entry.range(59, 0), a1 = entry.range(119, 60);
                    const ap_uint<60> b0 = entry.range(179, 120), b1 = entry.range(239, 180);
                    ap_uint<60> left = pass == 0 ? a0 : a1;
                    ap_uint<60> right = (pass == 0 || plaintext) ? b0 : b1;
                    bool negative = false;
                    if (pass == 2) {
                        const bool a_negative = a0 < a1, b_negative = b0 < b1;
                        left = a_negative ? ap_uint<60>(a1 - a0) : ap_uint<60>(a0 - a1);
                        right = b_negative ? ap_uint<60>(b1 - b0) : ap_uint<60>(b0 - b1);
                        negative = a_negative != b_negative;
                    }
                    const product_t value = left*right;
                    token.range(121*c + 119, 121*c) = value;
                    token[121*c + 120] = negative;
                }
                products.write(token);
            }
    }
}

void pipeline(const input_t* weights, const input_t* baby, hls::stream<products_t>& products,
              unsigned n, unsigned l, unsigned k, unsigned lane, bool plaintext) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream_of_blocks<Window, 2> windows;
#pragma HLS ARRAY_PARTITION variable=windows cyclic factor=8 dim=1
#pragma HLS BIND_STORAGE variable=windows type=RAM_2P impl=LUTRAM
    load(weights, baby, windows, n, l, k, lane, plaintext);
    multiply(windows, products, (n/TILE)*l*k, plaintext);
}
}

extern "C" int ct_reader(const input_t* weights, const input_t* baby, hls::stream<products_t>& products,
                         unsigned n, unsigned l, unsigned k, unsigned lane) {
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
    const bool plaintext = (k & plaintext_mode) != 0;
    k &= ~plaintext_mode;
    const int status = dimensions(n, l, k);
    if (status != OK) return status;
    if (n > MAX_N/2) return BAD_N;
    if (lane > 1) return 5;
    pipeline(weights, baby, products, n, l, k, lane, plaintext);
    return OK;
}
