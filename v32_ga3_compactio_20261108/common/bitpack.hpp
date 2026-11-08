#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
#include <stdexcept>
#include <vector>

// Lossless little-endian bit stream. No arithmetic approximation, quantization,
// changed modulus, or removal of nonzero residue bits. Every value is < q.
namespace compactbits {
inline unsigned width(uint64_t q){
    if(q<2 || q>=(uint64_t(1)<<60))throw std::runtime_error("compact modulus range");
    return 64-unsigned(__builtin_clzll(q));
}
inline size_t bytes(size_t count,unsigned w){
    if(!count || count%8 || !w || w>60 || count>SIZE_MAX/64)
        throw std::runtime_error("compact block dimensions");
    return count/8*w;
}
inline void encode(const uint64_t* src,size_t count,uint64_t q,uint8_t* dst){
    const unsigned w=width(q);const size_t length=bytes(count,w);
    // Every canonical block has 2*N words (N >=128), hence an exact number
    // of 64-bit packed words. Explicit LE stores keep the format portable.
    uint64_t acc=0;unsigned used=0;size_t pos=0;
    for(size_t i=0;i<count;++i){
        const uint64_t v=src[i];if(v>=q)throw std::runtime_error("compact input not canonical");
        acc|=v<<used;used+=w;
        if(used>=64){for(unsigned b=0;b<8;++b)dst[pos++]=uint8_t(acc>>(8*b));
            used-=64;acc=used?v>>(w-used):0;}
    }
    if(used%8)throw std::runtime_error("compact tail alignment");
    for(unsigned b=0;b<used/8;++b)dst[pos++]=uint8_t(acc>>(8*b));
    if(pos!=length)throw std::runtime_error("compact encoded length");
}
template<unsigned W> inline void decode_fixed(const uint8_t* src,size_t count,uint64_t q,uint64_t* dst){
    constexpr uint64_t mask=(uint64_t(1)<<W)-1;
    for(size_t i=0;i<count;i+=8,src+=W){
        for(unsigned j=0;j<8;++j){
            const unsigned byte=(j*W)/8,shift=(j*W)%8;
            uint64_t low;std::memcpy(&low,src+byte,8);
            uint64_t v=low>>shift;
            if(W+shift>64)v|=uint64_t(src[byte+8])<<(64-shift);
            v&=mask;if(v>=q)throw std::runtime_error("compact decoded residue not canonical");
            dst[i+j]=v;
        }
    }
}
// The caller supplies eight ZERO guard bytes beyond the exact packed payload.
// memcpy is safe for unaligned addresses and avoids C++ aliasing/lifetime UB.
inline void decode(const uint8_t* src,size_t count,uint64_t q,uint64_t* dst){
    const unsigned w=width(q);bytes(count,w);
    switch(w){
        case 45:decode_fixed<45>(src,count,q,dst);return;
        case 46:decode_fixed<46>(src,count,q,dst);return;
        case 51:decode_fixed<51>(src,count,q,dst);return;
        case 60:decode_fixed<60>(src,count,q,dst);return;
        default:break;
    }
    const uint64_t mask=(uint64_t(1)<<w)-1;
    for(size_t i=0;i<count;i+=8,src+=w)for(unsigned j=0;j<8;++j){
        unsigned byte=j*w/8,shift=j*w%8;uint64_t v;std::memcpy(&v,src+byte,8);
        v>>=shift;if(w+shift>64)v|=uint64_t(src[byte+8])<<(64-shift);
        v&=mask;if(v>=q)throw std::runtime_error("compact decoded residue not canonical");dst[i+j]=v;
    }
}
}
