#include "ct_mac.hpp"
#include <vector>
#include <stdexcept>
#include <iostream>
using namespace ctmac;
extern "C" int native_pl_chain(const input_t*,word_t*,const param_t*,unsigned,unsigned,unsigned);
static void check(bool ok,const char* s){if(!ok)throw std::runtime_error(s);}
int main(){try{
 const uint64_t qs[3]={(1ULL<<44)+1,(1ULL<<51)-129,(1ULL<<60)-1};param_t params[16]={};
 for(unsigned t=0;t<3;++t){params[t]=qs[t];params[t].range(191,64)=ap_uint<128>((ap_uint<129>(1)<<128)/qs[t]);}
 const uint64_t guard=0xa2856137fedc90b4ULL;uint64_t state=0x20261103;
 std::vector<input_t> input(3072);std::vector<word_t> out(1154);std::vector<uint64_t> source(24576);
 for(unsigned run=0;run<6;++run){unsigned n=run==0?64:128,l=3,k=run%2?16:1;
  for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j)for(unsigned c=0;c<4;++c){state=state*6364136223846793005ULL+1442695040888963407ULL;unsigned s=(p+t+j+c+run)%7;source[((p*l+t)*n+j)*4+c]=s==0?0:s==1?qs[t]-1:s==2?1:state%qs[t];}
  for(unsigned p=0;p<k;++p)for(unsigned c=0;c<4;++c)source[((p*l+2)*n)*4+c]=qs[2]-1;
  for(unsigned i=0;i<n*l*k*4/8;++i){input_t word=0;for(unsigned j=0;j<8;++j)word.range(64*j+63,64*j)=source[i*8+j];input[i]=word;}
  for(auto&x:out)x=guard;
  check(native_pl_chain(input.data(),out.data()+1,params,n,l,k)==0,"native chain status");
  check(out[0].to_uint64()==guard&&out[n*l*3+1].to_uint64()==guard,"native output canary");
  for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j){unsigned __int128 sums[3]={};for(unsigned p=0;p<k;++p){size_t i=((p*l+t)*n+j)*4;const auto*a=&source[i];sums[0]+=(unsigned __int128)a[0]*a[2];sums[1]+=(unsigned __int128)a[0]*a[3]+(unsigned __int128)a[1]*a[2];sums[2]+=(unsigned __int128)a[1]*a[3];}for(unsigned c=0;c<3;++c)check(out[1+(t*n+j)*3+c].to_uint64()==uint64_t(sums[c]%qs[t]),"native exact MAC mismatch");}
  std::cout<<"PASS_NATIVE_PL_CHAIN run="<<run<<" N="<<n<<" L="<<l<<" K="<<k<<" verified_words="<<n*l*3<<'\n';
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
