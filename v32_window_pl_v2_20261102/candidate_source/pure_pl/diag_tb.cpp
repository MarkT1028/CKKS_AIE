#include "ct_mac.hpp"
#include <vector>
#include <stdexcept>
#include <iostream>
using namespace ctmac;
extern "C" int ct_limb_diag(hls::stream<axis_t>&,hls::stream<axis_t>&,hls::stream<axis_t>&,unsigned,unsigned,unsigned);
static void check(bool b,const char* s){if(!b)throw std::runtime_error(s);}
int main(){try{
 for(unsigned run=0;run<4;++run){const unsigned n=run%2?128:64,l=run%2?3:1,k=run%2?3:1,frames=n/TILE*l*k*4;
  hls::stream<axis_t> left,right,out;std::vector<uint32_t> expected;
  uint64_t state=0x28020261102ULL+run;
  for(unsigned f=0;f<frames;++f){uint32_t a[4][64],b[4][64];
   for(unsigned r=0;r<4;++r)for(unsigned j=0;j<64;j+=8){axis_t x=0,y=0;for(unsigned lane=0;lane<8;++lane){state=state*6364136223846793005ULL+1;auto av=(run==0||f==0)?32767U:uint32_t(state>>32)&32767U;state=state*6364136223846793005ULL+1;auto bv=(run==0||f==0)?32767U:uint32_t(state>>32)&32767U;a[r][j+lane]=av;b[r][j+lane]=bv;x.range(16*lane+15,16*lane)=av;y.range(16*lane+15,16*lane)=bv;}left.write(x);right.write(y);}
   for(unsigned d=0;d<7;++d)for(unsigned j=0;j<64;++j){uint64_t s=0;for(unsigned r=0;r<4;++r)if(d>=r&&d-r<4)s+=uint64_t(a[r][j])*b[d-r][j];check(s<=0xffffffffULL,"diagonal overflow");expected.push_back(uint32_t(s));}
  }
  check(ct_limb_diag(left,right,out,n,l,k)==0,"status");size_t pos=0;while(!out.empty()){auto beat=out.read();for(unsigned lane=0;lane<4;++lane){check(pos<expected.size(),"extra output");check(beat.range(32*lane+31,32*lane).to_uint()==expected[pos++],"wrong exact diagonal");}}
  check(pos==expected.size()&&left.empty()&&right.empty(),"incomplete/drain");std::cout<<"PASS_PURE_PL_EXACT_DIAGONALS run="<<run<<" frames="<<frames<<" values="<<pos<<'\n';
 }
 hls::stream<axis_t> a,b,c;check(ct_limb_diag(a,b,c,63,1,1)==BAD_N&&c.empty(),"reject dimension");
 std::cout<<"PASS_PURE_PL_DIAGONAL_RESTART_AND_BOUNDARY\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
