#include "ct_mac.hpp"
#include <vector>
#include <iostream>
#include <stdexcept>
using namespace ctmac;
#ifndef PERF_COMPACT
#define PERF_COMPACT 0
#endif
#ifndef PERF_SINK
#define PERF_SINK 0
#endif
static void check(bool v,const char* why){if(!v)throw std::runtime_error(why);}
int main(){
try {
  const uint64_t qs[]={(1ULL<<44)+1,(1ULL<<51)-129,(1ULL<<60)-1};
  // Co-simulation adapters copy the declared m_axi depth, even though l=3.
  param_t params[MAX_L]={};
  for(unsigned t=0;t<3;++t){params[t]=qs[t];ap_uint<129> unit=ap_uint<129>(1)<<128;params[t].range(191,64)=ap_uint<128>(unit/qs[t]);}
  // Repeated calls verify draining/restart of bounded dataflow FIFOs.
  for(unsigned k:{1U,3U,16U,16U}) {
    const unsigned n=128,l=3;
    std::vector<uint64_t> in(n*l*k*4);
    uint64_t state=0x280+k;
    for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<l;++t)
      for(unsigned j=0;j<n;++j)for(unsigned c=0;c<4;++c){
        state=state*6364136223846793005ULL+1442695040888963407ULL;
        unsigned code=(pair+t+j+c)%5;
        in[((pair*l+t)*n+j)*4+c]=code==0?0:code==1?1:code==2?qs[t]-1:state%qs[t];
      }
    // Explicit diagonal beyond signed 32-bit range.
    for(unsigned pair=0;pair<k;++pair)for(unsigned c=0;c<4;++c)in[((pair*l+2)*n)*4+c]=qs[2]-1;
    hls::stream<axis_t> partials;
    uint64_t sums[4]={},xors[4]={};unsigned beats=0;
    for(unsigned t=0;t<l;++t)for(unsigned base=0;base<n;base+=64)
      for(unsigned pair=0;pair<k;++pair)for(unsigned product=0;product<4;++product) {
#if PERF_COMPACT
        for(unsigned d=0;d<7;++d)for(unsigned j=0;j<64;j+=4) {
          axis_t packed=0;
          for(unsigned lane=0;lane<4;++lane) {
            unsigned idx=((pair*l+t)*n+base+j+lane)*4;
            uint64_t a=in[idx+product/2],b=in[idx+2+product%2],sum=0;
            for(unsigned r=0;r<4;++r)if(d>=r&&d-r<4)sum+=((a>>(15*r))&32767)*((b>>(15*(d-r)))&32767);
            check(sum<=0xffffffffULL,"uint32 diagonal overflow");
            packed.range(32*lane+31,32*lane)=uint32_t(sum);
          }
          partials.write(packed);++beats;
        }
#else
        for(unsigned r=0;r<4;++r)for(unsigned s=0;s<4;++s)for(unsigned j=0;j<64;j+=4) {
          axis_t packed=0;
          for(unsigned lane=0;lane<4;++lane) {
            unsigned idx=((pair*l+t)*n+base+j+lane)*4;
            uint64_t a=(in[idx+product/2]>>(15*r))&32767,b=(in[idx+2+product%2]>>(15*s))&32767;
            uint64_t value=a*b;packed.range(32*lane+31,32*lane)=uint32_t(value);
            sums[lane]+=value;xors[lane]^=value<<(beats&31);
          }
          partials.write(packed);++beats;
        }
#endif
      }
    std::vector<word_t> out(393216,word_t(-1));
    check(ct_reduce_accum(partials,out.data(),params,n,l,k)==0,"top return error");
    check(partials.empty(),"stream not drained");
#if PERF_SINK
    check(out[0]==0x53494e4b44494147ULL&&out[1]==beats,"sink magic/count");
    for(unsigned lane=0;lane<4;++lane)check(out[2+lane]==sums[lane]&&out[6+lane]==xors[lane],"sink fingerprint mismatch");
    for(unsigned i=10;i<out.size();++i)check(out[i]==word_t(-1),"sink wrote beyond fingerprint");
#else
    for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j) {
      ap_uint<128> expected[3]={0,0,0};
      for(unsigned pair=0;pair<k;++pair) {
        unsigned idx=((pair*l+t)*n+j)*4;
        ap_uint<64> a=in[idx],b=in[idx+1],c=in[idx+2],d=in[idx+3];
        expected[0]+=ap_uint<128>(a)*c;expected[1]+=ap_uint<128>(a)*d+ap_uint<128>(b)*c;expected[2]+=ap_uint<128>(b)*d;
      }
      for(unsigned c=0;c<3;++c)check(out[(t*n+j)*3+c]==word_t(expected[c]%qs[t]),"RTL residue mismatch");
    }
#endif
    std::cout<<"PASS RTL_TB K="<<k<<" compact="<<PERF_COMPACT<<" sink="<<PERF_SINK<<" beats="<<beats<<std::endl;
  }
  return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<std::endl;return 1;}
}
