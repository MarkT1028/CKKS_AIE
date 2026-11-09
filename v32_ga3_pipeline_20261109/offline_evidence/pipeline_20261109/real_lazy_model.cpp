#include "ct_mac.hpp"
#include <filesystem>
#include <fstream>
#include <sstream>
#include <vector>
#include <cstring>
#include <iostream>
#include <stdexcept>
namespace fs=std::filesystem;using namespace ctmac;
extern "C" int native_pl_chain(const input_t*,word_t*,const param_t*,unsigned,unsigned,unsigned);
static void need(bool v,const char*s){if(!v)throw std::runtime_error(s);}
static uint64_t little(const uint8_t*p,unsigned n){uint64_t x=0;for(unsigned i=0;i<n;++i)x|=uint64_t(p[i])<<(8*i);return x;}
struct Record{unsigned l;std::vector<uint8_t> header;std::vector<uint64_t> words;};
static Record read(const fs::path&p,unsigned kind){
 std::ifstream f(p,std::ios::binary);need(bool(f),"real record open");Record r;r.header.resize(64);f.read((char*)r.header.data(),64);
 need(bool(f)&&std::memcmp(r.header.data(),"CKKSMAC1",8)==0&&little(r.header.data()+8,4)==1&&little(r.header.data()+12,4)==kind,"real record format");
 r.l=little(r.header.data()+20,4);need(little(r.header.data()+16,4)==8192&&r.l>0&&r.l<=16&&little(r.header.data()+24,4)==16,"real record shape");
 size_t n=little(r.header.data()+48,8);need(n==size_t(8192)*r.l*(kind==2?3:32),"real record words");r.header.resize(64+24*r.l);f.read((char*)r.header.data()+64,24*r.l);r.words.resize(n);f.read((char*)r.words.data(),n*8);need(bool(f)&&f.peek()==EOF,"real record length");return r;
}
int main(int argc,char**argv){try{
 need(argc==2||argc==5,"real_lazy_model PUBLIC_DATA [CT GROUP COEFFICIENT]");
 const unsigned want_ct=argc==5?std::stoul(argv[2]):0,want_group=argc==5?std::stoul(argv[3]):0,want_coefficient=argc==5?std::stoul(argv[4]):0;
 need(want_ct<16&&want_group<4&&want_coefficient<131072&&want_coefficient%8192==0,"selected real coordinates");
 const fs::path root=argv[1];std::ifstream jobs(root/"jobs.tsv");std::string row;std::getline(jobs,row);uint64_t checked=0;unsigned shards=0;
 while(std::getline(jobs,row)){
  std::istringstream in(row);unsigned id,ct,g,tower,c,n,l,k;std::string a,b,gold;need(bool(in>>id>>ct>>g>>tower>>c>>n>>l>>k>>a>>b>>gold),"job");
  if(ct!=want_ct||g!=want_group||c!=want_coefficient)continue;
  auto A=read(root/a,3),B=read(root/b,4),G=read(root/gold,2);need(A.l==l&&B.l==l&&G.l==l&&std::equal(A.header.begin()+64,A.header.end(),G.header.begin()+64)&&std::equal(B.header.begin()+64,B.header.end(),G.header.begin()+64),"moduli mismatch");
  param_t params[16]={};for(unsigned t=0;t<l;++t){const auto*p=G.header.data()+64+24*t;params[t]=little(p,8);params[t].range(127,64)=little(p+8,8);params[t].range(191,128)=little(p+16,8);need(valid_parameter(params[t]),"bad actual parameter");}
  for(unsigned lane=0;lane<2;++lane){const unsigned half=4096;std::vector<input_t> input(size_t(half)*l*k/2);std::vector<word_t> output(size_t(half)*l*3+2);for(auto&v:output)v=~uint64_t(0);
   for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<half;j+=2){input_t wide=0;
    for(unsigned v=0;v<2;++v){const size_t s=((size_t(pair)*l+t)*8192+lane*half+j+v)*2;uint64_t x[4]={A.words[s],A.words[s+1],B.words[s],B.words[s+1]};for(unsigned q=0;q<4;++q){need(x[q]<params[t].range(63,0).to_uint64(),"noncanonical input");wide.range(256*v+64*q+63,256*v+64*q)=x[q];}}
    input[((size_t(pair)*l+t)*half+j)/2]=wide;
   }
   need(native_pl_chain(input.data(),output.data()+1,params,half,l,k)==0,"lazy chain status");need(output.front()==word_t(~uint64_t(0))&&output.back()==word_t(~uint64_t(0)),"output canary");
   for(unsigned t=0;t<l;++t)for(unsigned j=0;j<half*3;++j){size_t dst=size_t(t)*8192*3+lane*half*3+j;need(output[1+size_t(t)*half*3+j].to_uint64()==G.words[dst],"actual real lazy result mismatch");++checked;}
  }
  ++shards;std::cout<<"PASS_REAL_LAZY8_AP tower="<<tower<<" L="<<l<<" cumulative_words="<<checked<<std::endl;
 }
 need(shards==4&&checked==1302528,"all53 moduli and full coefficient range");std::cout<<"PASS_REAL_LAZY8_ALL_53_MODULI_1302528_WORDS software_only=1 ct="<<want_ct<<" group="<<want_group<<" coefficient="<<want_coefficient<<'\n';return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
