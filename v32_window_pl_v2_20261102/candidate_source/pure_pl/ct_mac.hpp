#pragma once
#include <ap_int.h>
#include <hls_stream.h>

namespace ctmac {
constexpr unsigned TILE = 64;
constexpr unsigned MAX_N = 8192;
constexpr unsigned MAX_L = 16;
constexpr unsigned MAX_K = 16;
using word_t = ap_uint<64>;
using axis_t = ap_uint<128>;
using param_t = ap_uint<192>;
using product_t = ap_uint<120>;
using reciprocal_t = ap_uint<84>;
enum Status { OK=0, BAD_N=1, BAD_L=2, BAD_K=3, BAD_PARAMETER=4 };
inline int dimensions(unsigned n,unsigned l,unsigned k) {
#pragma HLS INLINE
    if(n<TILE || n>MAX_N || (n&(n-1))!=0) return BAD_N;
    if(l==0 || l>MAX_L) return BAD_L;
    if(k==0 || k>MAX_K) return BAD_K;
    return OK;
}
inline bool valid_parameter(param_t p) {
#pragma HLS INLINE
    word_t q=p.range(63,0);
    ap_uint<128> mu=p.range(191,64);
    if(q<(word_t(1)<<44) || q>=(word_t(1)<<60) || !q[0] ||
       mu.range(127,84)!=0) return false;
    // Verify floor(2^128/q) without a hardware division.
    ap_uint<145> scaled=ap_uint<145>(q)*ap_uint<145>(mu);
    ap_uint<145> unit=ap_uint<145>(1)<<128;
    return scaled<=unit && scaled+ap_uint<145>(q)>unit;
}
inline word_t reduce(product_t product,ap_uint<60> q,reciprocal_t mu) {
#pragma HLS INLINE
    // For product<q^2 and mu=floor(2^128/q), quotient is at most one low.
    ap_uint<204> scaled=ap_uint<204>(product)*ap_uint<204>(mu);
    ap_uint<64> quotient=scaled.range(191,128);
    ap_uint<120> times_q=ap_uint<120>(quotient)*ap_uint<120>(q);
    ap_uint<121> remainder=ap_uint<121>(product)-ap_uint<121>(times_q);
    if(remainder>=q) remainder-=q;
    return word_t(remainder);
}
inline word_t add_mod(word_t a,word_t b,ap_uint<60> q) {
#pragma HLS INLINE
    ap_uint<65> sum=ap_uint<65>(a)+ap_uint<65>(b);
    if(sum>=q) sum-=q;
    return word_t(sum);
}
}

extern "C" int ct_reader(const ctmac::word_t* inputs,
    hls::stream<ctmac::axis_t>& left,hls::stream<ctmac::axis_t>& right,
    unsigned n,unsigned l,unsigned k);
extern "C" int ct_reduce_accum(hls::stream<ctmac::axis_t>& partials,
    ctmac::word_t* outputs,const ctmac::param_t* params,
    unsigned n,unsigned l,unsigned k);
