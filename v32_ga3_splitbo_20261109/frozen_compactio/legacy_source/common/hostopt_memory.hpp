#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#if defined(__aarch64__)
#include <arm_neon.h>
#endif

// Pure memory transforms; no XRT, arithmetic, fixture changes or BO reads.
namespace ga3mem {
constexpr size_t block_coefficients=1024;
inline void interleave(const uint64_t* weight,const uint64_t* baby,uint64_t* out,size_t count){
    size_t i=0;
#if defined(__aarch64__)
    for(;i+2<=count;i+=2){
        const auto a=vld2q_u64(weight+2*i),b=vld2q_u64(baby+2*i);
        uint64x2x4_t v;v.val[0]=a.val[0];v.val[1]=a.val[1];v.val[2]=b.val[0];v.val[3]=b.val[1];
        vst4q_u64(out+4*i,v);
    }
#endif
    for(;i<count;++i){out[4*i]=weight[2*i];out[4*i+1]=weight[2*i+1];out[4*i+2]=baby[2*i];out[4*i+3]=baby[2*i+1];}
}
inline void pack(const uint64_t* weight,const uint64_t* baby,uint64_t* out,
                 unsigned full_n,unsigned l,unsigned k,unsigned lane,unsigned lanes,bool burst,bool fill_baby=true){
    if(!weight||!baby||!out||!lanes||lanes>2||lane>=lanes||full_n%lanes||!l||!k)
        throw std::runtime_error("hostopt pack dimensions");
    const size_t n=full_n/lanes;
    // 32 KiB per preparation worker, not a second whole-window input copy.
    alignas(64) std::array<uint64_t,block_coefficients*4> scratch;
    for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t){
        const size_t source=((size_t(p)*l+t)*full_n+lane*n)*2,dest=(size_t(p)*l+t)*n*4;
        if(!burst){
            if(fill_baby)interleave(weight+source,baby+source,out+dest,n);
            else for(size_t i=0;i<n;++i){
#if defined(__aarch64__)
                vst1q_u64(out+dest+4*i,vld1q_u64(weight+source+2*i));
#else
                out[dest+4*i]=weight[source+2*i];out[dest+4*i+1]=weight[source+2*i+1];
#endif
            }
            continue;
        }
        for(size_t i=0;i<n;i+=block_coefficients){
            const size_t count=std::min(block_coefficients,n-i);
            interleave(weight+source+2*i,baby+source+2*i,scratch.data(),count);
            std::memcpy(out+dest+4*i,scratch.data(),count*4*sizeof(uint64_t));
        }
    }
}
inline void merge_verify(unsigned n,unsigned l,unsigned lane,const uint64_t* source,
                         size_t words,const uint64_t* expected,uint64_t* merged){
    if(!source||!expected||!merged||lane>=2||n%2||!l||words!=size_t(n/2)*l*3)
        throw std::runtime_error("hostopt merge dimensions");
    const size_t count=size_t(n/2)*3,bytes=count*sizeof(uint64_t);
    for(unsigned t=0;t<l;++t){
        const size_t local=size_t(t)*count,global=(size_t(t)*n+lane*(n/2))*3;
        std::memcpy(merged+global,source+local,bytes);
        if(std::memcmp(merged+global,expected+global,bytes)!=0)
            throw std::runtime_error("hostopt complete output mismatch");
    }
}
}
