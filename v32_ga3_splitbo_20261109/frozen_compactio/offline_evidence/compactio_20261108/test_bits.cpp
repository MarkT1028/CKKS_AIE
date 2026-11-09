#include "../../board_packages/v32_ga3_compactio_20261108/common/bitpack.hpp"
#include <iostream>
#include <random>
#include <array>
#include <fstream>
#include <string>
int main(int argc,char**argv){
 std::mt19937_64 random(0xabc1024);size_t checks=0;
 for(unsigned w=2;w<=60;++w){
  uint64_t q=(uint64_t(1)<<(w-1))+1+(w>2?(uint64_t(1)<<(w-2)):0);
  for(size_t n:{size_t(8),size_t(16),size_t(256),size_t(16384)}){
   std::vector<uint64_t> src(n),out(n+2,0xdeadbeef);
   for(size_t i=0;i<n;++i)src[i]=i%7==0?0:i%7==1?q-1:random()%q;
   auto len=compactbits::bytes(n,w);std::vector<uint8_t> packed(len+8,0);
   compactbits::encode(src.data(),n,q,packed.data());compactbits::decode(packed.data(),n,q,out.data()+1);
   if(out.front()!=0xdeadbeef||out.back()!=0xdeadbeef||!std::equal(src.begin(),src.end(),out.begin()+1))return 2;
   // Independent, intentionally slow bit-by-bit oracle, separate from both
   // the reservoir encoder and eight-value decoder.
   for(size_t i=0;i<n;++i){uint64_t v=0;for(unsigned b=0;b<w;++b){size_t bit=i*w+b;v|=uint64_t((packed[bit/8]>>(bit%8))&1)<<b;}if(v!=src[i])return 3;}
   ++checks;
   if(argc==2&&n==256){std::string prefix=std::string(argv[1])+"/w"+std::to_string(w);
    std::ofstream a(prefix+".raw",std::ios::binary),b(prefix+".packed",std::ios::binary);
    a.write(reinterpret_cast<const char*>(src.data()),src.size()*8);b.write(reinterpret_cast<const char*>(packed.data()),len);}
  }
  bool caught=false;try{uint64_t src[8]={q};uint8_t dst[64]={};compactbits::encode(src,8,q,dst);}catch(...){caught=true;}if(!caught)return 4;
  std::vector<uint8_t> bad(compactbits::bytes(8,w)+8,0xff);std::vector<uint64_t> out(8);
  caught=false;try{compactbits::decode(bad.data(),8,q,out.data());}catch(...){caught=true;}if(!caught)return 5;
 }
 for(unsigned w:{0,61,64}){bool caught=false;try{compactbits::bytes(8,w);}catch(...){caught=true;}if(!caught)return 6;}
 std::cout<<"PASS_INDEPENDENT_BIT_ORACLE widths=2..60 blocks="<<checks<<" noncanonical_rejected=118\n";
}
