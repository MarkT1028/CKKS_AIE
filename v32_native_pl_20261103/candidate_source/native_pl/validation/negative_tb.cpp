#include "ct_mac.hpp"
#include <iostream>
#include <stdexcept>
using namespace ctmac;
static void need(bool a,const char*s){if(!a)throw std::runtime_error(s);}
int main(){try{hls::stream<products_t> stream;word_t output[192];for(auto&v:output)v=0xabcdef1234567890ULL;param_t p[16]={};unsigned cases=0;
 const unsigned bad[][3]={{0,1,1},{63,1,1},{65,1,1},{16384,1,1},{64,0,1},{64,17,1},{64,1,0},{64,1,17}};
 for(auto&d:bad){need(ct_reader(nullptr,stream,d[0],d[1],d[2])!=OK,"reader bad dimensions accepted");need(stream.empty(),"reader emitted on bad dimensions");need(ct_reduce_accum(stream,output,p,d[0],d[1],d[2])!=OK,"reducer bad dimensions accepted");++cases;}
 for(uint64_t q:{uint64_t(0),uint64_t(1),uint64_t(1)<<43,uint64_t(1)<<44,uint64_t(1)<<60}){p[0]=q;need(ct_reduce_accum(stream,output,p,64,1,1)==BAD_PARAMETER,"bad q accepted");need(stream.empty(),"bad q consumed stream");++cases;}
 for(unsigned mode=0;mode<3;++mode){uint64_t q=(1ULL<<60)-1;param_t a=q;ap_uint<128> mu=(ap_uint<129>(1)<<128)/q;if(mode==0)mu=0;else if(mode==1)mu+=1;else mu-=1;a.range(191,64)=mu;p[0]=a;need(ct_reduce_accum(stream,output,p,64,1,1)==BAD_PARAMETER,"bad reciprocal accepted");++cases;}
 for(auto v:output)need(v==word_t(0xabcdef1234567890ULL),"invalid call modified output");
 uint64_t state=0x28061103;for(unsigned bits:{45U,46U,51U,59U,60U})for(unsigned t=0;t<3000;++t){state=state*6364136223846793005ULL+1;uint64_t q=((uint64_t(1)<<(bits-1))|(state&((uint64_t(1)<<(bits-1))-1))|1);ap_uint<84> mu=(ap_uint<129>(1)<<128)/q;state=state*6364136223846793005ULL+1;uint64_t a=t%4==0?q-1:state%q;state=state*6364136223846793005ULL+1;uint64_t b=t%4==0?q-1:state%q;product_t prod=ap_uint<60>(a)*ap_uint<60>(b);need(reduce(prod,ap_uint<60>(q),mu).to_uint64()==uint64_t((unsigned __int128)a*b%q),"independent native Barrett mismatch");++cases;}
 std::cout<<"PASS_NATIVE_INVALID_INPUT_AND_INDEPENDENT_BARRETT cases="<<cases<<" no_board=1\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
