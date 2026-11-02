#define CPU_BENCH_NO_MAIN
#include "../reference/cpu/cpu_bench.cpp"
#include "../reference/common/dataset_cache.hpp"
#include "../common/compact_dataset.hpp"
#include "../common/mapped_source.hpp"
#include "../common/replay.hpp"
int main(int argc,char**argv){try{
 require(argc==2||argc==3,"usage: stream_source_test DATA [--mutate-stamp]");streamio::Dataset source(argv[1]);CachedDataset old;std::vector<uint64_t> full(source.input_words()),merged(source.shape.output_words());std::array<std::vector<uint64_t>,2> lanes;for(auto& x:lanes)x.resize(source.input_words()/2);source.begin_request();uint64_t checked=0;
 if(argc==3){require(std::string(argv[2])=="--mutate-stamp","source test option");auto file=fs::path(argv[1])/"shared/chunk_0_baby.bin";auto old=fs::last_write_time(file);fs::last_write_time(file,old+std::chrono::seconds(2));bool caught=false;try{source.pack(0,0,0,1,full.data(),full.size());}catch(...){caught=true;}fs::last_write_time(file,old);require(caught,"source mutation not rejected");std::cout<<"PASS_MAPPED_SOURCE_MUTATION_REJECTED\n";return 0;}
 for(unsigned g=0;g<6;++g){load_compact_group(old,argv[1],g);require(old.chunks.size()==source.dimensions.chunks,"source test grid");for(unsigned i=0;i<source.dimensions.chunks;++i){source.pack(g,i,0,1,full.data(),full.size());require(full==old.chunks[i].input.words,"stream full pack differs from original compact loader");for(unsigned l=0;l<2;++l){source.pack(g,i,l,2,lanes[l].data(),lanes[l].size());InputCase ref;fill_shard_block(old.chunks[i].input,l,ref);require(lanes[l]==ref.words,"direct lane pack differs from original split");std::vector<uint64_t> half(ref.output_words());for(unsigned t=0;t<ref.l;++t)std::copy_n(old.chunks[i].expected.data()+(size_t(t)*source.shape.n+l*ref.n)*3,ref.n*3,half.data()+size_t(t)*ref.n*3);boexp::merge_from(source.shape,l,half.data(),half.size(),merged);}source.verify(g,i,merged);checked+=merged.size();auto bad=merged;bad[bad.size()/2]^=1;bool caught=false;try{source.verify(g,i,bad);}catch(...){caught=true;}require(caught,"stream output corruption accepted");}}
 source.end_request();require(checked==source.verified_words(),"stream source test coverage");std::cout<<"PASS_STREAM_SOURCE_FULL_AND_LANE_PACK_EXACT groups=6 checked_words="<<checked<<" corrupted_output_rejected=1\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
