#pragma once
#include <map>
#include <set>
#include <memory>
#include "record.hpp"
#include "packed_input.hpp"

namespace { namespace finishopt {
struct Block {unsigned tower,coefficient,l;};
struct Window {
    InputCase shape;unsigned tower=0,coefficient=0,ct=0,mask=0;bool active=false;
    std::vector<uint64_t> baby;
    std::array<std::shared_ptr<const std::vector<uint64_t>>,4> weights;
    std::string baby_key;
    std::array<std::string,4> weight_keys,expected,digests;
    void begin(){require(!active&&!baby.empty(),"window begin ownership");active=true;mask=0;digests.fill("");}
    void verify(unsigned g,const std::string& digest){
        require(active&&g<4&&!(mask&(1U<<g)),"duplicate/unowned output verification");
        require(digest==expected[g],"complete canonical output SHA256 mismatch");digests[g]=digest;mask|=1U<<g;
    }
    void end(){require(active&&mask==15,"window missing full output verification");active=false;}
};
struct Job {unsigned id,ct,group,tower,coefficient,n,l,k;fs::path a,b,gold;};
class Source {
    fs::path root,cache;std::set<std::string> packed;
    std::map<std::tuple<unsigned,unsigned,unsigned,unsigned>,Job> jobs;
    std::map<std::string,std::string> hashes;
    std::array<std::shared_ptr<const std::vector<uint64_t>>,4> weights;
    std::array<std::string,4> keys;
    std::array<InputCase,4> weight_shapes;
    std::vector<uint8_t> scratch;
    windowio::ReadStats counters;
    void read_record(const fs::path& path,unsigned kind,InputCase& shape,std::vector<uint64_t>& words){
        auto tick=Clock::now();windowio::Record record(root/path,kind);counters.header_ms+=windowio::ReadStats::ms(tick);
        shape.n=record.shape.n;shape.l=record.shape.l;shape.k=record.shape.k;shape.parameters=record.shape.parameters;
        const auto digest=hashes.at(path.generic_string());
        if(packed.count(digest))windowio::read_packed(cache/"inputs"/(digest+".qpk"),record,digest,words,scratch,&counters);
        else record.read_canonical_into(words,&counters);
        tick=Clock::now();record.retire();counters.retire_ms+=windowio::ReadStats::ms(tick);
    }
public:
    std::vector<Block> blocks;unsigned full_l=0,coefficient_windows=0;uint64_t full_words=0;
    explicit Source(const fs::path& path):root(fs::canonical(path)){
        const char* p=std::getenv("V32_GA3_CACHE");require(p&&*p,"explicit compact cache required");cache=fs::canonical(p);
        require(root!=cache,"cache/source alias");
        std::ifstream manifest(root/"SHA256SUMS_DATA");std::string line;require(bool(manifest),"data manifest missing");
        while(std::getline(manifest,line)){
            require(line.size()>66&&line.substr(64,2)=="  ","source manifest syntax");
            const auto name=line.substr(66),hash=line.substr(0,64);fs::path rel(name);
            require(rel.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos&&hash.find_first_not_of("0123456789abcdef")==std::string::npos,"unsafe manifest entry");
            require(hashes.emplace(name,hash).second,"duplicate manifest entry");
        }
        std::ifstream index(cache/"CACHE_INDEX.tsv");require(bool(std::getline(index,line))&&line=="canonical_sha256\tpacked_sha256\tbytes","compact index syntax");
        while(std::getline(index,line)){
            std::istringstream row(line);std::string hash,stored,extra;uint64_t bytes;
            require(bool(row>>hash>>stored>>bytes)&&!(row>>extra)&&hash.size()==64&&stored.size()==64&&hash.find_first_not_of("0123456789abcdef")==std::string::npos&&stored.find_first_not_of("0123456789abcdef")==std::string::npos&&bytes>128&&bytes<64ULL*1024*1024,"unsafe cache index");
            require(packed.insert(hash).second,"duplicate cache entry");
        }
        require(!packed.empty(),"empty declared cache");
        std::ifstream shape_file(root/"shape.json");require(bool(shape_file)&&fs::file_size(root/"shape.json")<16384,"shape missing/large");
        std::string shape_text((std::istreambuf_iterator<char>(shape_file)),{});
        require(shape_uint(shape_text,"N")==131072&&shape_uint(shape_text,"K")==16&&shape_uint(shape_text,"output_ciphertexts")==16&&shape_uint(shape_text,"groups_per_output")==4,"real ga3 shape");
        full_l=shape_uint(shape_text,"L");coefficient_windows=shape_uint(shape_text,"coefficient_windows");
        require(full_l>16&&full_l<=64&&(coefficient_windows==2||coefficient_windows==16),"RNS/coefficient coverage");
        full_words=64ULL*8192*coefficient_windows*full_l*3;
        std::ifstream table(root/"jobs.tsv");require(bool(std::getline(table,line))&&line=="id\toutput_ct\tgroup\ttower_start\tcoefficient_start\tN\tL\tK\tA\tB\texpected","jobs header");unsigned id=0;
        while(std::getline(table,line)){
            Job j;std::string a,b,gold,extra;std::istringstream row(line);
            require(bool(row>>j.id>>j.ct>>j.group>>j.tower>>j.coefficient>>j.n>>j.l>>j.k>>a>>b>>gold)&&!(row>>extra),"jobs fields");
            require(j.id==id++&&j.ct<16&&j.group<4&&j.tower%16==0&&j.tower<full_l&&j.l==std::min(16U,full_l-j.tower)&&j.n==8192&&j.k==16&&j.coefficient%8192==0&&j.coefficient<131072,"jobs shape/coverage");
            for(const auto& name:{a,b,gold}){
                fs::path rel(name);require(rel.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos&&fs::is_regular_file(root/rel)&&!fs::is_symlink(root/rel)&&hashes.count(name),"unsafe/missing data record");
            }
            j.a=a;j.b=b;j.gold=gold;require(jobs.emplace(std::make_tuple(j.tower,j.coefficient,j.ct,j.group),j).second,"duplicate job");
        }
        require(id==64U*coefficient_windows*((full_l+15)/16)&&id==shape_uint(shape_text,"jobs"),"incomplete jobs count");
        for(unsigned t=0;t<full_l;t+=16)for(unsigned c=0;c<131072;c+=8192){
            if(coefficient_windows==2&&c!=0&&c!=122880)continue;
            blocks.push_back({t,c,std::min(16U,full_l-t)});
            for(unsigned ct=0;ct<16;++ct)for(unsigned g=0;g<4;++g)require(jobs.count({t,c,ct,g})==1,"missing job coordinate");
        }
    }
    void admit(const Block& block,unsigned ct,Window& out){
        require(!out.active&&ct<16,"admit active context");
        const auto& first=jobs.at({block.tower,block.coefficient,ct,3});
        InputCase shape;read_record(first.b,4,shape,out.baby);
        require(shape.n==8192&&shape.l==block.l&&shape.k==16,"selected record shape");
        out.shape=shape;out.tower=block.tower;out.coefficient=block.coefficient;out.ct=ct;out.baby_key=first.b.generic_string();out.mask=0;
        for(unsigned g=0;g<4;++g){
            const auto& job=jobs.at({block.tower,block.coefficient,ct,g});require(job.b==first.b,"baby must be shared across four groups");
            const auto key=job.a.generic_string();
            if(keys[g]!=key){
                auto words=std::make_shared<std::vector<uint64_t>>();InputCase ws;read_record(job.a,3,ws,*words);
                weights[g]=words;weight_shapes[g]=std::move(ws);keys[g]=key;
            }
            require(same_parameters(shape,weight_shapes[g]),"weight/baby parameters differ");
            out.weights[g]=weights[g];out.weight_keys[g]=key;out.expected[g]=hashes.at(job.gold.generic_string());
        }
    }
    const windowio::ReadStats& stats()const{return counters;}
};
} }
