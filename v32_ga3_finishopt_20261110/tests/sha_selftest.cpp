#include <cstdint>
#include <algorithm>
#include <vector>
#include <random>
#include <iostream>
#include <thread>
#include "../common/sealed_sha256.hpp"
#include <common/sealed_sha256.hpp>
struct Param{uint64_t q,mu_lo,mu_hi;};
struct Shape{unsigned n,l,k;std::vector<Param> parameters;size_t output_words()const{return size_t(n)*l*3;}};
static void need(bool b,const char* message){if(!b)throw std::runtime_error(message);}
int main(){try{
    finishsha::Engine candidate;sealedsha::Engine parent;std::mt19937_64 random(8175261);unsigned checked=0;
    for(unsigned n:{128U,256U,8192U})for(unsigned l:{1U,3U,5U,16U}){
        Shape shape{n,l,16,{}};for(unsigned t=0;t<l;++t)shape.parameters.push_back({(1ULL<<51)-129-t*2,17+t,0});
        std::vector<uint64_t> canonical(shape.output_words()),left(canonical.size()/2),right(left.size());
        for(auto& v:canonical)v=random()%((1ULL<<51)-1000);
        const size_t half=size_t(n/2)*3;
        for(unsigned t=0;t<l;++t){std::copy_n(canonical.data()+t*half*2,half,left.data()+t*half);std::copy_n(canonical.data()+t*half*2+half,half,right.data()+t*half);}
        const auto expected=sealedsha::output_digest(parent,shape,canonical);
        need(finishsha::output_digest(candidate,shape,canonical)==expected,"merged digest differs from parent");
        need(finishsha::split_output_digest(candidate,shape,left.data(),right.data(),left.size())==expected,"segmented canonical digest differs");
        right.back()^=1;need(finishsha::split_output_digest(candidate,shape,left.data(),right.data(),left.size())!=expected,"corruption missed");right.back()^=1;
        need(finishsha::split_output_digest(candidate,shape,right.data(),left.data(),left.size())!=expected,"lane reversal missed");
        if(l>1){const auto header=finishsha::canonical_header(shape,canonical.size());const auto wrong=candidate.segments(header.data(),header.size(),[&](auto add){add(left.data(),left.size()*8);add(right.data(),right.size()*8);});need(wrong!=expected,"wrong tower order missed");}
        bool rejected=false;try{finishsha::split_output_digest(candidate,shape,left.data(),right.data(),left.size()-1);}catch(...){rejected=true;}need(rejected,"short output accepted");
        std::array<std::thread,2> threads;std::array<bool,2> ok{};
        for(unsigned i=0;i<2;++i)threads[i]=std::thread([&,i]{ok[i]=finishsha::split_output_digest(candidate,shape,left.data(),right.data(),left.size())==expected;});
        for(auto& t:threads)t.join();need(ok[0]&&ok[1],"independent context concurrency mismatch");++checked;
    }
    std::cout<<"PASS_EXACT_CANONICAL_SEGMENTED_SHA cases="<<checked<<" parent_equivalence corruption lane_tower_order short_output independent_contexts=1\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
