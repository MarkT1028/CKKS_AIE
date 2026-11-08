#define CKKSMAC_PARSER_ONLY
#define FULL_HS4_BACKEND_ONLY
#define GA3_SUPPRESS_LEGACY_MAIN
#include "../../board_packages/v32_ga3_hostopt_20261108/variants/v32_core_2_pipe/host/bo_host.cpp"
#include "../../board_packages/v32_ga3_hostopt_20261108/common/record.hpp"
#include <cassert>
int main(int argc,char** argv){
 assert(argc==2);fs::path root=argv[1];std::vector<uint64_t> output;windowio::ReadStats stats;
 for(unsigned kind:{3U,4U,2U}){
  output.clear();uint64_t* retained=nullptr;
  for(unsigned l:{16U,16U,5U,16U}){
   windowio::Record r(root/("record_"+std::to_string(kind)+"_"+std::to_string(l)+".bin"),kind);
   r.read_canonical_into(output,&stats);auto expected=r.read_canonical();assert(output==expected);
   if(l==16&&retained)assert(output.data()==retained);if(l==16)retained=output.data();
   std::fill(output.begin(),output.end(),UINT64_MAX);r.read_canonical_into(output,&stats);assert(output==expected);
  }
 }
 assert(stats.records==24&&stats.bytes>0&&stats.pread_ms>=0&&stats.range_ms>=0);
 std::cout<<"PASS_REUSE_READ_BUFFER_FULL_EQUIVALENCE_AND_L16_L5_L16 records="<<stats.records<<" bytes="<<stats.bytes<<'\n';
}
