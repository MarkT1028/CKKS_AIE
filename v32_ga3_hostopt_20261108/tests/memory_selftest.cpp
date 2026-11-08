#include "hostopt_memory.hpp"
#include <vector>
#include <random>
#include <thread>
#include <iostream>
#include <cassert>
int main(){
 std::mt19937_64 rng(0xA1530245);uint64_t cases=0,words=0;
 for(unsigned n:{128U,256U,8192U})for(unsigned l:{1U,5U,16U})for(unsigned k:{1U,16U}){
  std::vector<uint64_t>a(size_t(n)*l*k*2),b(a.size());for(auto&x:a)x=rng();for(auto&x:b)x=rng();
  for(bool burst:{false,true}){
   std::array<std::vector<uint64_t>,2> dest;const size_t len=size_t(n/2)*l*k*4;
   for(auto&v:dest)v.assign(len+8,0xCDCDCDCDCDCDCDCDULL);
   std::array<std::thread,2> workers;
   for(unsigned lane=0;lane<2;++lane)workers[lane]=std::thread([&,lane]{ga3mem::pack(a.data(),b.data(),dest[lane].data()+3,n,l,k,lane,2,burst);});
   for(auto&t:workers)t.join();
   for(unsigned lane=0;lane<2;++lane){auto&d=dest[lane];for(size_t j=0;j<3;++j)assert(d[j]==0xCDCDCDCDCDCDCDCDULL);for(size_t j=3+len;j<d.size();++j)assert(d[j]==0xCDCDCDCDCDCDCDCDULL);
    for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n/2;++j){size_t src=((size_t(p)*l+t)*n+lane*(n/2)+j)*2,i=3+((size_t(p)*l+t)*(n/2)+j)*4;assert(d[i]==a[src]&&d[i+1]==a[src+1]&&d[i+2]==b[src]&&d[i+3]==b[src+1]);}words+=len;
   }
   for(auto&x:a)x^=0x1234567812345678ULL;
   for(unsigned lane=0;lane<2;++lane){auto&d=dest[lane];ga3mem::pack(a.data(),b.data(),d.data()+3,n,l,k,lane,2,burst,false);
    for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n/2;++j){size_t src=((size_t(p)*l+t)*n+lane*(n/2)+j)*2,i=3+((size_t(p)*l+t)*(n/2)+j)*4;assert(d[i]==a[src]&&d[i+1]==a[src+1]&&d[i+2]==b[src]&&d[i+3]==b[src+1]);}
   }
   ++cases;
  }
  const size_t outwords=size_t(n)*l*3;std::vector<uint64_t>gold(outwords),merged(outwords+8,UINT64_MAX);for(auto&x:gold)x=rng()&((1ULL<<59)-1);
  std::array<std::vector<uint64_t>,2> lane_out;
  for(unsigned lane=0;lane<2;++lane){auto&v=lane_out[lane];v.resize(outwords/2);for(unsigned t=0;t<l;++t)std::copy_n(gold.data()+(size_t(t)*n+lane*(n/2))*3,size_t(n/2)*3,v.data()+size_t(t)*(n/2)*3);ga3mem::merge_verify(n,l,lane,v.data(),v.size(),gold.data(),merged.data()+3);}
  assert(std::equal(gold.begin(),gold.end(),merged.begin()+3));assert(merged[0]==UINT64_MAX&&merged[outwords+3]==UINT64_MAX);
  for(unsigned lane=0;lane<2;++lane)for(size_t idx:{size_t(0),lane_out[lane].size()-1}){lane_out[lane][idx]^=1;bool rejected=false;try{ga3mem::merge_verify(n,l,lane,lane_out[lane].data(),lane_out[lane].size(),gold.data(),merged.data()+3);}catch(const std::runtime_error&){rejected=true;}assert(rejected);lane_out[lane][idx]^=1;}
 }
#if defined(__aarch64__)
 std::cout<<"ARM64_NEON ";
#else
 std::cout<<"X86_PORTABLE ";
#endif
 std::cout<<"PASS_HOSTOPT_RANDOM_PACK_MERGE_CORRUPTION cases="<<cases<<" words="<<words<<"\n";
}
