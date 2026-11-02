#include "ct_mac.hpp"
#include <vector>
#include <stdexcept>
#include <iostream>
using namespace ctmac;
extern "C" int pure_pl_chain(const word_t*,word_t*,const param_t*,unsigned,unsigned,unsigned);
static void check(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
int main(){try{
 uint64_t qs[3]={(1ULL<<44)+1,(1ULL<<51)-129,(1ULL<<60)-1};param_t params[16]={};for(unsigned t=0;t<3;++t){params[t]=qs[t];params[t].range(191,64)=ap_uint<128>((ap_uint<129>(1)<<128)/qs[t]);}
 std::vector<word_t> input(24576),output(1152);uint64_t state=0x28061102;
 for(unsigned run=0;run<4;++run){unsigned n=128,l=3,k=run%2?16:1;
  for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j)for(unsigned c=0;c<4;++c){state=state*6364136223846793005ULL+1442695040888963407ULL;unsigned s=(p+t+j+c+run)%5;input[((p*l+t)*n+j)*4+c]=s==0?0:s==1?qs[t]-1:state%qs[t];}
  // Maximum60-bit limbs, including a diagonal larger than signed32-bit.
  for(unsigned p=0;p<k;++p)for(unsigned c=0;c<4;++c)input[((p*l+2)*n)*4+c]=qs[2]-1;
  for(auto& x:output)x=~uint64_t(0);check(pure_pl_chain(input.data(),output.data(),params,n,l,k)==0,"chain status");
  for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j){unsigned __int128 expected[3]={};for(unsigned p=0;p<k;++p){size_t x=((p*l+t)*n+j)*4;uint64_t a0=input[x].to_uint64(),a1=input[x+1].to_uint64(),b0=input[x+2].to_uint64(),b1=input[x+3].to_uint64();expected[0]+=(unsigned __int128)a0*b0;expected[1]+=(unsigned __int128)a0*b1+(unsigned __int128)a1*b0;expected[2]+=(unsigned __int128)a1*b1;}for(unsigned c=0;c<3;++c)check(output[(t*n+j)*3+c].to_uint64()==uint64_t(expected[c]%qs[t]),"full raw CKKS MAC mismatch");}
  std::cout<<"PASS_FULL_PURE_PL_MAC run="<<run<<" n="<<n<<" l="<<l<<" k="<<k<<" verified_words="<<n*l*3<<'\n';
 }return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
