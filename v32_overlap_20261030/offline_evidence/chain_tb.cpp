#include "record_io.hpp"
#include <sstream>
int main(){try{
  const std::string root="/home/mark/v32_coreopt_20261029/chain/";
  for(unsigned lane=0;lane<2;++lane){
    auto expected=read_record(root+"expected"+std::to_string(lane)+".bin");
    param_t params[MAX_L]={};for(unsigned t=0;t<expected.l;++t)params[t]=expected.params[t];
    hls::stream<axis_t> partials;std::ifstream f(root+"partials"+std::to_string(lane)+".txt");check(bool(f),"partials input");
    unsigned beats=0;uint64_t word;
    while(f>>word){axis_t beat=word;check(word<=0xffffffffULL,"lane0 overflow");for(unsigned c=1;c<4;++c){check(bool(f>>word)&&word<=0xffffffffULL,"truncated beat");beat.range(32*c+31,32*c)=uint32_t(word);}partials.write(beat);++beats;}
    check(beats==896*112,"beat count");std::vector<word_t> output(393216,word_t(-1));
    check(ct_reduce_accum(partials,output.data(),params,64,14,16)==OK,"RTL status");check(partials.empty(),"undrained AIE data");
    for(unsigned i=0;i<expected.words.size();++i)check(output[i]==expected.words[i],"AIE->RTL full residue mismatch");
    for(unsigned i=expected.words.size();i<output.size();++i)check(output[i]==word_t(-1),"RTL wrote beyond exact result");
    std::cout<<"PASS ACTUAL_AIE_TO_REDUCER_RTL lane="<<lane<<" beats="<<beats<<" verified_words="<<expected.words.size()<<std::endl;
  }return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
