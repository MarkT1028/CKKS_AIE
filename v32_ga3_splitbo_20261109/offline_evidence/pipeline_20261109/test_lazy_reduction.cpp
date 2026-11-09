#include "native_reduce.cpp"
#include <iostream>
#include <random>
int main(){
 std::mt19937_64 rng(0x20261109);uint64_t cases=0;
 for(unsigned bits=44;bits<=60;++bits){
  uint64_t q=(uint64_t(1)<<bits)-1;if(bits==44)q=(uint64_t(1)<<44)+1;
  param_t p=q;p.range(191,64)=ap_uint<128>((ap_uint<129>(1)<<128)/q);
  if(!valid_parameter(p))return 1;reciprocal_t mu=p.range(147,64);
  for(unsigned i=0;i<2048;++i){
   unsigned __int128 value=(static_cast<unsigned __int128>(rng())<<64)|rng();
   if(i==0)value=static_cast<unsigned __int128>(32)*(q-1)*(q-1);
   if(i==1)value=~static_cast<unsigned __int128>(0);
   if(i==2)value=0;if(i==3)value=q-1;if(i==4)value=q;if(i==5)value=q+1;
   ap_uint<128> x=uint64_t(value);x.range(127,64)=uint64_t(value>>64);
   if(reduce_sum(x,ap_uint<60>(q),mu).to_uint64()!=uint64_t(value%q))return 2;
   ++cases;
  }
 }
 hls::stream<products_t> empty;word_t out[8];param_t bad[16]={};
 if(ct_reduce_accum(empty,out,bad,63,1,1)!=BAD_N)return 3;
 if(ct_reduce_accum(empty,out,bad,64,0,1)!=BAD_L)return 4;
 if(ct_reduce_accum(empty,out,bad,64,1,17)!=BAD_K)return 5;
 if(ct_reduce_accum(empty,out,bad,64,1,1)!=BAD_PARAMETER)return 6;
 std::cout<<"PASS_EXACT_LAZY_REDUCTION cases="<<cases<<" widths=44..60 full_uint128=1 bad_parameters_before_stream_read=1\n";
}
