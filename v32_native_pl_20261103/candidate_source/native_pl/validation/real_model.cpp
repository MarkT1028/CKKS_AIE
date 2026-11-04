#include "ct_mac.hpp"
#include <fstream>
#include <iostream>
#include <vector>
#include <filesystem>
#include <cstring>
#include <stdexcept>
using namespace ctmac;namespace fs=std::filesystem;
extern "C" int native_pl_chain(const input_t*,word_t*,const param_t*,unsigned,unsigned,unsigned);
static void need(bool a,const char*s){if(!a)throw std::runtime_error(s);}
struct Record{unsigned n,l,k,kind;std::vector<unsigned char> header;std::vector<uint64_t> data;};
static uint64_t u(const unsigned char*p,unsigned n){uint64_t x=0;for(unsigned i=0;i<n;++i)x|=uint64_t(p[i])<<(8*i);return x;}
static Record read(const fs::path&p,unsigned wanted){std::ifstream f(p,std::ios::binary);need(bool(f),"record open");Record r;r.header.resize(64);f.read((char*)r.header.data(),64);auto h=r.header.data();need(std::memcmp(h,"CKKSMAC1",8)==0&&u(h+8,4)==1&&u(h+12,4)==wanted,"record header");r.kind=wanted;r.n=u(h+16,4);r.l=u(h+20,4);r.k=u(h+24,4);need(r.n==8192&&r.l==14&&r.k==16,"real shape");size_t words=u(h+48,8);need(words==size_t(r.n)*r.l*(wanted==2?3:2*r.k),"real word count");r.header.resize(64+24*r.l);f.read((char*)r.header.data()+64,24*r.l);r.data.resize(words);f.read((char*)r.data.data(),words*8);need(bool(f)&&f.peek()==EOF,"record exact length");return r;}
int main(int argc,char**argv){try{need(argc==3,"real_model DATA NEW_OUTPUT");fs::path root=argv[1],out=argv[2];need(!fs::exists(out),"new output only");fs::create_directories(out);uint64_t checked=0;
 for(unsigned chunk=0;chunk<16;++chunk){auto stem="chunk_"+std::to_string(chunk);auto B=read(root/"shared"/(stem+"_baby.bin"),4);
  for(unsigned group=0;group<6;++group){auto dir=root/("group_"+std::to_string(group))/"chunks";auto A=read(dir/(stem+"_weight.bin"),3),gold=read(dir/(stem+"_expected.bin"),2);need(A.header.size()==B.header.size()&&std::equal(A.header.begin()+64,A.header.end(),B.header.begin()+64)&&std::equal(A.header.begin()+64,A.header.end(),gold.header.begin()+64),"real moduli mismatch");
   param_t params[16]={};for(unsigned t=0;t<14;++t){auto*p=gold.header.data()+64+24*t;params[t]=u(p,8);params[t].range(127,64)=u(p+8,8);params[t].range(191,128)=u(p+16,8);need(valid_parameter(params[t]),"real parameter");}
   const unsigned n=4096,l=14,k=16;std::vector<uint64_t> merged(gold.data.size(),~uint64_t(0));
   for(unsigned lane=0;lane<2;++lane){std::vector<input_t> input(size_t(n)*l*k/2);std::vector<word_t> result(size_t(n)*l*3+2);for(auto&v:result)v=~uint64_t(0);
    for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;j+=2){input_t wide=0;uint64_t q=params[t].range(63,0).to_uint64();for(unsigned c=0;c<2;++c){size_t s=((size_t(pair)*l+t)*8192+lane*n+j+c)*2;uint64_t v[4]={A.data[s],A.data[s+1],B.data[s],B.data[s+1]};for(unsigned a=0;a<4;++a){need(v[a]<q,"noncanonical real input");wide.range(256*c+64*a+63,256*c+64*a)=v[a];}}input[((size_t(pair)*l+t)*n+j)/2]=wide;}
    need(native_pl_chain(input.data(),result.data()+1,params,n,l,k)==0,"real native status");need(result.front()==word_t(~uint64_t(0))&&result.back()==word_t(~uint64_t(0)),"real output canary");
    for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n*3;++j){auto v=result[1+size_t(t)*n*3+j].to_uint64();size_t dst=size_t(t)*8192*3+lane*n*3+j;need(v==gold.data[dst],"real AP model mismatch");merged[dst]=v;++checked;}
   }
   auto dest=out/("group_"+std::to_string(group));fs::create_directories(dest);std::ofstream f(dest/(stem+"_output.bin"),std::ios::binary);f.write((char*)gold.header.data(),gold.header.size());f.write((char*)merged.data(),merged.size()*8);f.close();need(bool(f),"model output save");std::cout<<"PASS_NATIVE_REAL_AP group="<<group<<" chunk="<<chunk<<" cumulative_verified_words="<<checked<<'\n'<<std::flush;
  }
 }need(checked==33030144,"complete real model coverage");std::cout<<"PASS_NATIVE_REAL_AP_ALL_96_CHUNKS_33030144_WORDS software_only_not_board=1\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
