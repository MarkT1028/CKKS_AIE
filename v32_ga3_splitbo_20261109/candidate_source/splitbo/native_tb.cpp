#include "ct_mac.hpp"
#include <vector>
#include <stdexcept>
#include <iostream>
using namespace ctmac;
extern "C" int native_split_chain(const input_t*,const input_t*,word_t*,const param_t*,unsigned,unsigned,unsigned,unsigned);
static void check(bool ok,const char*s){if(!ok)throw std::runtime_error(s);}
int main(){try{
 const uint64_t qs[3]={(1ULL<<44)+1,(1ULL<<51)-129,(1ULL<<60)-1};param_t params[16]={};
 for(unsigned t=0;t<16;++t){params[t]=qs[t%3];params[t].range(191,64)=ap_uint<128>((ap_uint<129>(1)<<128)/qs[t%3]);}
 uint64_t state=0x20261109,guard=0xdead259164348ac1ULL;
 std::vector<input_t> a(16384),b(16384);std::vector<uint64_t> av(131072),bv(131072);std::vector<word_t> out(6146);
 for(unsigned run=0;run<6;++run){unsigned n=run<2?64:128,l=run<2?3:run<4?16:5,k=run<2?1:16,lane=run%2;
  const unsigned words=2*n*l*k*2;
  for(unsigned p=0;p<k;++p)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<2*n;++j)for(unsigned c=0;c<2;++c){
   size_t i=((size_t(p)*l+t)*(2*n)+j)*2+c;uint64_t q=qs[t%3];state=state*6364136223846793005ULL+1442695040888963407ULL;
   av[i]=(j+p+c+run)%3?state%q:q-1;state=state*6364136223846793005ULL+1442695040888963407ULL;bv[i]=(j+p+c+run)%5?state%q:q-1;
  }
  for(unsigned p=0;p<k;++p)for(unsigned c=0;c<2;++c){av[((p*l+2)*(2*n)+lane*n)*2+c]=qs[2]-1;bv[((p*l+2)*(2*n)+lane*n)*2+c]=qs[2]-1;}
  for(unsigned i=0;i<words/8;++i){input_t x=0,y=0;for(unsigned c=0;c<8;++c){x.range(64*c+63,64*c)=av[8*i+c];y.range(64*c+63,64*c)=bv[8*i+c];}a[i]=x;b[i]=y;}
  for(auto&v:out)v=guard;
  check(native_split_chain(a.data(),b.data(),out.data()+1,params,n,l,k,lane)==0,"split status");
  check(out.front().to_uint64()==guard&&out[n*l*3+1].to_uint64()==guard,"output canary");
  for(unsigned t=0;t<l;++t)for(unsigned j=0;j<n;++j){unsigned __int128 sums[3]={};
   for(unsigned p=0;p<k;++p){size_t i=((size_t(p)*l+t)*(2*n)+lane*n+j)*2;sums[0]+=(unsigned __int128)av[i]*bv[i];sums[1]+=(unsigned __int128)av[i]*bv[i+1]+(unsigned __int128)av[i+1]*bv[i];sums[2]+=(unsigned __int128)av[i+1]*bv[i+1];}
   for(unsigned c=0;c<3;++c)check(out[1+(t*n+j)*3+c].to_uint64()==uint64_t(sums[c]%qs[t%3]),"split canonical MAC mismatch");
  }
  std::cout<<"PASS_SPLIT N="<<n<<" L="<<l<<" K="<<k<<" lane="<<lane<<" words="<<n*l*3<<'\n';
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
