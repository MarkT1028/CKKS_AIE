#include "ct_mac.hpp"

using namespace ctmac;

namespace {
// With canonical q < 2^60 and K <= 16, the largest output sum is < 2^125.
// Barrett's quotient for this nonnegative 128-bit input is at most one low.
word_t reduce_sum(ap_uint<128> sum, ap_uint<60> q, reciprocal_t mu) {
#pragma HLS INLINE
    const ap_uint<212> scaled = ap_uint<212>(sum)*ap_uint<212>(mu);
    const ap_uint<84> quotient = scaled.range(211, 128);
    const ap_uint<144> times_q = ap_uint<144>(quotient)*ap_uint<144>(q);
    ap_uint<145> remainder = ap_uint<145>(sum) - ap_uint<145>(times_q);
    if (remainder >= q) remainder -= q;
    return word_t(remainder);
}

void accumulate(hls::stream<products_t>& products, word_t* outputs, const param_t cached[MAX_L],
                unsigned n, unsigned l, unsigned k, bool plaintext) {
#pragma HLS INLINE off
    ap_uint<128> sums[3][TILE];
#pragma HLS ARRAY_PARTITION variable=sums complete dim=1
#pragma HLS ARRAY_PARTITION variable=sums cyclic factor=8 dim=2
    const unsigned passes = plaintext ? 2 : 3;
    for (unsigned t = 0; t < l; ++t) {
        const ap_uint<60> q = cached[t].range(59, 0);
        const reciprocal_t mu = cached[t].range(147, 64);
        for (unsigned base = 0; base < n; base += TILE) {
            for (unsigned pair = 0; pair < k; ++pair)
                for (unsigned pass = 0; pass < passes; ++pass)
                    for (unsigned j = 0; j < TILE; j += 8) {
#pragma HLS PIPELINE II=1
                        const products_t token = products.read();
                        for (unsigned lane = 0; lane < 8; ++lane) {
#pragma HLS UNROLL
                            const bool negative = token[121*lane + 120];
                            const ap_uint<128> magnitude = token.range(121*lane + 119, 121*lane);
                            ap_uint<128> previous = 0;
                            if (pair != 0) previous = sums[pass][j + lane];
                            const ap_uint<128> term = negative ? ap_uint<128>(~magnitude) : magnitude;
                            sums[pass][j + lane] = previous + term + ap_uint<1>(negative);
                        }
                    }
            for (unsigned j = 0; j < TILE; ++j)
                for (unsigned c = 0; c < passes; ++c) {
#pragma HLS PIPELINE II=1
                    ap_uint<128> value = sums[c][j];
                    if (!plaintext && c == 1) {
                        // (a0-a1)(b0-b1) is accumulated modulo 2^128. This
                        // difference yields the exact nonnegative cross sum.
                        value = sums[0][j] + sums[1][j] - sums[2][j];
                    }
                    if (!plaintext && c == 2) value = sums[1][j];
                    outputs[(t*n + base + j)*passes + c] = reduce_sum(value, q, mu);
                }
        }
    }
}
}

extern "C" int ct_reduce_accum(hls::stream<products_t>& products, word_t* outputs,
                               const param_t* params, unsigned n, unsigned l, unsigned k) {
#pragma HLS INTERFACE axis port=products
#pragma HLS INTERFACE m_axi port=outputs offset=slave bundle=gmem0 depth=196608 max_write_burst_length=64
#pragma HLS INTERFACE m_axi port=params offset=slave bundle=gmem1 depth=16
#pragma HLS INTERFACE s_axilite port=outputs bundle=control
#pragma HLS INTERFACE s_axilite port=params bundle=control
#pragma HLS INTERFACE s_axilite port=n bundle=control
#pragma HLS INTERFACE s_axilite port=l bundle=control
#pragma HLS INTERFACE s_axilite port=k bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control
    const bool plaintext = (k & plaintext_mode) != 0;
    k &= ~plaintext_mode;
    const int status = dimensions(n, l, k);
    if (status != OK) return status;
    if (n > MAX_N/2) return BAD_N;
    param_t cached[MAX_L];
    for (unsigned t = 0; t < l; ++t) {
        cached[t] = params[t];
        if (!valid_parameter(cached[t])) return BAD_PARAMETER;
    }
    accumulate(products, outputs, cached, n, l, k, plaintext);
    return OK;
}
