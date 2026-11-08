#pragma once
#include "record.hpp"
#include "hostopt_memory.hpp"
#include "sealed_sha256.hpp"
#include <map>
#include <set>

namespace { namespace windowio {
struct Job {unsigned id,ct,group,tower,coefficient,n,l,k;fs::path a,b,gold;};
struct Block {unsigned tower,coefficient,l;};
class Dataset {
 fs::path root;std::map<std::tuple<unsigned,unsigned,unsigned,unsigned>,Job> jobs;
 std::array<std::vector<uint64_t>,4> weights,golden;std::vector<uint64_t> baby;
 std::array<fs::path,4> weight_paths;std::array<InputCase,4> weight_shapes;unsigned mask=0;std::array<unsigned,4> verified_lanes{};bool active=false;ReadStats stats;
 std::map<std::string,std::string> sealed_hashes;std::array<std::string,4> expected_hashes,verified_hashes;
 std::unique_ptr<sealedsha::Engine> hash_engine;uint64_t hashed_outputs=0,hashed_bytes=0,gold_read_bytes_avoided=0;
 void verify_hash(unsigned g,const std::vector<uint64_t>& output){
  require(hash_engine&&g<4&&output.size()==shape.output_words(),"complete SHA256 output shape");
  const auto actual=sealedsha::output_digest(*hash_engine,shape,output);
  require(actual==expected_hashes[g],"complete canonical output SHA256 mismatch");verified_hashes[g]=actual;
  ++hashed_outputs;hashed_bytes+=64+24ULL*shape.l+output.size()*8;
 }
 static void matching(const InputCase&a,const InputCase&b){require(same_parameters(a,b),"ga3 record shape/modulus differs");}
 void read_into(const fs::path&p,unsigned kind,InputCase& s,std::vector<uint64_t>& v){
  auto start=std::chrono::steady_clock::now();Record r(root/p,kind);stats.header_ms+=ReadStats::ms(start);s.n=r.shape.n;s.l=r.shape.l;s.k=r.shape.k;s.parameters=r.shape.parameters;
  r.read_canonical_into(v,&stats);auto retire=std::chrono::steady_clock::now();r.retire();stats.retire_ms+=ReadStats::ms(retire);
 }
public:
 InputCase shape;std::vector<Block> blocks;unsigned full_l=0,coefficient_windows=0;uint64_t full_words=0;bool actual_sample=false;
 explicit Dataset(const fs::path& p):root(fs::canonical(p)){
#if GA3_IO_PROFILE==2
  hash_engine=std::make_unique<sealedsha::Engine>();
  std::ifstream manifest(root/"SHA256SUMS_DATA");require(bool(manifest),"sealed original data manifest required");
  std::string entry;while(std::getline(manifest,entry)){
   require(entry.size()>66&&entry.substr(64,2)=="  ","sealed manifest syntax");
   const auto digest=entry.substr(0,64),name=entry.substr(66);
   require(digest.find_first_not_of("0123456789abcdef")==std::string::npos,"invalid sealed SHA256");
   fs::path rel(name);require(rel.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos,"sealed manifest unsafe path");
   require(sealed_hashes.emplace(name,digest).second,"duplicate sealed manifest entry");
  }
#endif
  std::ifstream sf(root/"shape.json");require(bool(sf)&&fs::file_size(root/"shape.json")<16384,"ga3 shape file");std::string text((std::istreambuf_iterator<char>(sf)),{});
  require(shape_uint(text,"N")==131072&&shape_uint(text,"K")==16&&shape_uint(text,"output_ciphertexts")==16&&shape_uint(text,"groups_per_output")==4,"full real ga3 dimensions");
  full_l=shape_uint(text,"L");coefficient_windows=shape_uint(text,"coefficient_windows");require(full_l>16&&full_l<=64&&(coefficient_windows==2||coefficient_windows==16),"complete ga3 RNS towers/declared coefficient scope");full_words=64ULL*8192*coefficient_windows*full_l*3;
  std::ifstream f(root/"jobs.tsv");std::string line;require(bool(std::getline(f,line))&&line=="id\toutput_ct\tgroup\ttower_start\tcoefficient_start\tN\tL\tK\tA\tB\texpected","ga3 job header");unsigned id=0;
  while(std::getline(f,line)){std::istringstream row(line);Job j;std::string a,b,g,extra;
   require(bool(row>>j.id>>j.ct>>j.group>>j.tower>>j.coefficient>>j.n>>j.l>>j.k>>a>>b>>g)&&!(row>>extra),"ga3 job fields");
   require(j.id==id++&&j.ct<16&&j.group<4&&j.tower%16==0&&j.tower<full_l&&j.l==std::min(16U,full_l-j.tower)&&j.n==8192&&j.k==16&&j.coefficient%8192==0&&j.coefficient<131072,"ga3 job coverage/shape");
   for(const auto& name:{a,b,g}){fs::path q(name);require(q.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos,"unsafe ga3 data path");require(fs::is_regular_file(root/q)&&!fs::is_symlink(root/q),"ga3 data file missing/unsafe");}
   j.a=a;j.b=b;j.gold=g;require(jobs.emplace(std::make_tuple(j.tower,j.coefficient,j.ct,j.group),j).second,"duplicate ga3 job");
  }
  require(id==64U*coefficient_windows*((full_l+15)/16)&&id==shape_uint(text,"jobs"),"incomplete declared ga3 job count");
  for(unsigned t=0;t<full_l;t+=16)for(unsigned c=0;c<131072;c+=8192){if(coefficient_windows==2&&c!=0&&c!=122880)continue;blocks.push_back({t,c,std::min(16U,full_l-t)});
   for(unsigned ct=0;ct<16;++ct)for(unsigned g=0;g<4;++g)require(jobs.count({t,c,ct,g})==1,"missing ga3 coordinate");}
  // Max BO allocation; the final shorter RNS shard is configured at runtime.
  shape.n=8192;shape.l=16;shape.k=16;
 }
 void admit(const Block& block,unsigned ct){
  require(!active&&ct<16,"ga3 admission while active");InputCase bs;
  const auto& first=jobs.at({block.tower,block.coefficient,ct,3});read_into(first.b,4,bs,baby);
  require(bs.n==8192&&bs.l==block.l&&bs.k==16,"ga3 selected shape");shape=std::move(bs);
  for(unsigned g=0;g<4;++g){const auto& j=jobs.at({block.tower,block.coefficient,ct,g});require(j.b==first.b,"ga3 baby must be shared across four groups");InputCase s;
   if(weight_paths[g]!=j.a){read_into(j.a,3,s,weights[g]);weight_shapes[g]=s;weight_paths[g]=j.a;}matching(shape,weight_shapes[g]);
#if GA3_IO_PROFILE==2
   const auto found=sealed_hashes.find(j.gold.generic_string());require(found!=sealed_hashes.end(),"missing sealed original output SHA256");
   expected_hashes[g]=found->second;gold_read_bytes_avoided+=shape.output_words()*8;
#else
   read_into(j.gold,2,s,golden[g]);matching(shape,s);
#endif
   require(weights[g].size()==size_t(shape.n)*shape.l*32,"ga3 retained weight length");
  }
 }
 void begin_request(){require(!active&&!baby.empty(),"ga3 begin state");active=true;mask=0;verified_lanes.fill(0);}
 void complete_coverage(){require(active&&mask==15,"ga3 four-group verified coverage");}
 void end_request(){complete_coverage();active=false;}
 void cancel_request()noexcept{active=false;}
 void cache_baby(unsigned chunk){require(active&&chunk==0,"ga3 window baby index");}
 size_t input_words()const{return size_t(shape.n)*shape.l*shape.k*4;}
 void pack_cached(unsigned g,unsigned chunk,unsigned lane,unsigned lanes,uint64_t* dest,size_t count,bool fill){
  require(active&&g<4&&chunk==0&&(lanes==1||lanes==2)&&lane<lanes&&dest&&count==input_words()/lanes,"ga3 lane pack arguments");unsigned n=shape.n/lanes;
  for(unsigned pair=0;pair<16;++pair)for(unsigned t=0;t<shape.l;++t){size_t src=((size_t(pair)*shape.l+t)*shape.n+lane*n)*2,dst=(size_t(pair)*shape.l+t)*n*4;
   for(unsigned j=0;j<n;++j){dest[dst+4*j]=weights[g][src+2*j];dest[dst+4*j+1]=weights[g][src+2*j+1];if(fill){dest[dst+4*j+2]=baby[src+2*j];dest[dst+4*j+3]=baby[src+2*j+1];}}
  }
 }
 void pack_optimized(unsigned g,unsigned lane,uint64_t* dest,size_t count,bool burst,bool fill_baby=true){
  require(active&&g<4&&lane<2&&dest&&count==input_words()/2,"hostopt pack arguments");
  ga3mem::pack(weights[g].data(),baby.data(),dest,shape.n,shape.l,shape.k,lane,2,burst,fill_baby);
 }
 void merge_verify_lane(unsigned g,unsigned lane,const uint64_t* source,size_t words,std::vector<uint64_t>& out){
  require(active&&g<4&&lane<2&&out.size()==shape.output_words()&&!(verified_lanes[g]&(1U<<lane)),"hostopt lane ownership");
#if GA3_IO_PROFILE==2
  require(source&&words==size_t(shape.n/2)*shape.l*3,"SHA256 lane shape");
  for(unsigned t=0;t<shape.l;++t)std::memcpy(out.data()+(size_t(t)*shape.n+lane*(shape.n/2))*3,
      source+size_t(t)*(shape.n/2)*3,size_t(shape.n/2)*3*sizeof(uint64_t));
  verified_lanes[g]|=1U<<lane;if(verified_lanes[g]==3)verify_hash(g,out);
#else
  ga3mem::merge_verify(shape.n,shape.l,lane,source,words,golden[g].data(),out.data());verified_lanes[g]|=1U<<lane;
#endif
 }
 void verify(unsigned g,unsigned chunk,const std::vector<uint64_t>& out){require(active&&g<4&&chunk==0,"CPU verification state");
#if GA3_IO_PROFILE==2
  verify_hash(g,out);
#else
  require(out==golden[g],"ga3 complete output mismatch");
#endif
  verified_lanes[g]=3;
 }
 uint64_t digest_count()const{return hashed_outputs;}
 uint64_t digest_bytes()const{return hashed_bytes;}
 uint64_t avoided_gold_bytes()const{return gold_read_bytes_avoided;}
 std::string digest_backend()const{return hash_engine?hash_engine->description():"none";}
 const std::string& verified_digest(unsigned g)const{
  require(active&&g<4&&verified_lanes[g]==3&&(mask&(1U<<g))&&verified_hashes[g].size()==64,"export requires this request's verified full output");
  return verified_hashes[g];
 }
 const ReadStats& admission_stats()const{return stats;}
 void retire_job(unsigned g,unsigned chunk,bool){require(active&&g<4&&chunk==0&&verified_lanes[g]==3&&!(mask&(1U<<g)),"ga3 duplicate verified group");mask|=1U<<g;}
 const std::vector<uint64_t>& expected(unsigned g)const{return golden.at(g);}
};
} }
