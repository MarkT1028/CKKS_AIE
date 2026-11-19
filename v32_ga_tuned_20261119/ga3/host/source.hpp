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
    struct PackedFile { std::string digest; uint64_t bytes; };
    fs::path root,cache;
    std::map<std::string,PackedFile> packed;
    std::map<std::tuple<unsigned,unsigned,unsigned,unsigned>,Job> jobs;
    std::map<std::string,std::string> hashes;
    std::array<std::shared_ptr<const std::vector<uint64_t>>,4> weights;
    std::array<std::string,4> keys;
    std::array<InputCase,4> weight_shapes;
    std::vector<uint8_t> scratch;
    windowio::ReadStats counters;
    std::unique_ptr<finishsha::Engine> network_hash;
    uint64_t received_bytes = 0;
    double received_hash_ms = 0;

    void read_network(const fs::path& path, unsigned kind, unsigned l, InputCase& shape,
                      std::vector<uint64_t>& words) {
        const std::array<unsigned,10> fields{1,kind,8192,l,16,2,1,64,0,0};
        std::array<uint8_t,64+24*16> header{};
        const size_t header_bytes = 64+24*l;
        const auto& digest = hashes.at(path.generic_string());
        const auto entry = packed.find(digest);
        const bool compressed = entry!=packed.end();
        auto tick = Clock::now();
        words.resize(size_t(8192)*l*16*2);
        const size_t bytes = words.size()*sizeof(uint64_t);
        if (compressed) scratch.resize(entry->second.bytes+8);
        counters.allocate_ms += windowio::ReadStats::ms(tick);
        tick = Clock::now();
        if (compressed) {
            ga_stream::fetch("ga3cache", "inputs/"+digest+".qpk", {{scratch.data(),entry->second.bytes}});
        } else {
            ga_stream::fetch("ga3", path.generic_string(), {{header.data(),header_bytes},{words.data(),bytes}});
        }
        counters.pread_ms += windowio::ReadStats::ms(tick);
        if (compressed) {
            tick = Clock::now();
            require(network_hash->hex(nullptr,0,scratch.data(),entry->second.bytes)==entry->second.digest,
                    "network GA3 packed file SHA256 differs from cache index");
            received_hash_ms += windowio::ReadStats::ms(tick);
            require(entry->second.bytes>128+header_bytes && std::memcmp(scratch.data(),"GA3QPK01",8)==0 &&
                    windowio::little(scratch.data()+8,4)==1 && windowio::little(scratch.data()+12,4)==header_bytes &&
                    windowio::little(scratch.data()+16,8)==entry->second.bytes-128-header_bytes &&
                    windowio::little(scratch.data()+24,8)==header_bytes+bytes &&
                    std::memcmp(scratch.data()+32,digest.data(),digest.size())==0 &&
                    std::all_of(scratch.begin()+96,scratch.begin()+128,[](uint8_t b){return b==0;}),
                    "invalid network GA3 packed wrapper");
            std::memcpy(header.data(),scratch.data()+128,header_bytes);
            std::fill(scratch.begin()+entry->second.bytes,scratch.end(),0);
        }
        tick = Clock::now();
        require(std::memcmp(header.data(),"CKKSMAC1",8)==0,"network GA3 input magic");
        for (size_t i = 0; i < fields.size(); ++i)
            require(windowio::little(header.data()+8+4*i,4)==fields[i],"network GA3 input header");
        require(windowio::little(header.data()+48,8)==words.size() && windowio::little(header.data()+56,8)==0,
                "network GA3 input length or reserved field");
        shape.n = 8192; shape.l = l; shape.k = 16;
        for (unsigned t = 0; t < l; ++t) {
            const auto* at = header.data()+64+24*t;
            Parameter parameter{windowio::little(at,8),windowio::little(at+8,8),windowio::little(at+16,8)};
            validate_parameter(parameter,t);
            shape.parameters.push_back(parameter);
        }
        counters.header_ms += windowio::ReadStats::ms(tick);
        if (compressed) {
            tick = Clock::now();
            constexpr size_t count=8192*2;
            const size_t size=entry->second.bytes-128-header_bytes;
            size_t offset=0, index=0;
            for (unsigned k=0;k<16;++k) for (const auto& p:shape.parameters) {
                const auto span=compactbits::bytes(count,compactbits::width(p.q));
                require(offset<=size && span<=size-offset,"invalid network GA3 packed length");
                compactbits::decode(scratch.data()+128+header_bytes+offset,count,p.q,words.data()+index);
                offset+=span;index+=count;
            }
            require(offset==size&&index==words.size(),"network GA3 packed length differs");
            counters.decode_ms += windowio::ReadStats::ms(tick);
            ++counters.packed_records;
            counters.packed_payload_bytes += size;
            counters.bytes += size;
            received_bytes += entry->second.bytes;
        } else {
            ++counters.raw_records;
            counters.bytes += bytes;
            received_bytes += header_bytes+bytes;
        }
        tick = Clock::now();
        require(network_hash->hex(header.data(),header_bytes,words.data(),bytes)==digest,
                "network GA3 input SHA256 differs from sealed data");
        received_hash_ms += windowio::ReadStats::ms(tick);
        ++counters.records;
        counters.logical_bytes += bytes;
    }

    void read_record(const fs::path& path,unsigned kind,unsigned l,InputCase& shape,std::vector<uint64_t>& words){
        if (network_hash) {
            read_network(path, kind, l, shape, words);
            return;
        }
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
        if (ga_stream::enabled()) network_hash = std::make_unique<finishsha::Engine>();
        else {
            const char* p=std::getenv("V32_GA3_CACHE");require(p&&*p,"explicit compact cache required");cache=fs::canonical(p);
            require(root!=cache,"cache/source alias");
        }
        std::ifstream manifest(root/"SHA256SUMS_DATA");std::string line;require(bool(manifest),"data manifest missing");
        while(std::getline(manifest,line)){
            require(line.size()>66&&line.substr(64,2)=="  ","source manifest syntax");
            const auto name=line.substr(66),hash=line.substr(0,64);fs::path rel(name);
            require(rel.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos&&hash.find_first_not_of("0123456789abcdef")==std::string::npos,"unsafe manifest entry");
            require(hashes.emplace(name,hash).second,"duplicate manifest entry");
        }
        const char* network_index=std::getenv("V32_GA3_NET_CACHE_INDEX");
        if (!network_hash || (network_index&&*network_index)) {
            const fs::path index_path=network_hash?fs::path(network_index):cache/"CACHE_INDEX.tsv";
            std::ifstream index(index_path);require(bool(std::getline(index,line))&&line=="canonical_sha256\tpacked_sha256\tbytes","compact index syntax");
            while(std::getline(index,line)){
                std::istringstream row(line);std::string hash,stored,extra;uint64_t bytes;
                require(bool(row>>hash>>stored>>bytes)&&!(row>>extra)&&hash.size()==64&&stored.size()==64&&hash.find_first_not_of("0123456789abcdef")==std::string::npos&&stored.find_first_not_of("0123456789abcdef")==std::string::npos&&bytes>128&&bytes<64ULL*1024*1024,"unsafe cache index");
                require(packed.emplace(hash,PackedFile{stored,bytes}).second,"duplicate cache entry");
            }
            require(!packed.empty(),"empty declared cache");
        }
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
                fs::path rel(name);require(rel.is_relative()&&name.find("..") == std::string::npos&&name.find('\\')==std::string::npos&&hashes.count(name),"unsafe/unsealed data record");
                require(network_hash || (fs::is_regular_file(root/rel)&&!fs::is_symlink(root/rel)),"missing local data record");
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
        InputCase shape;read_record(first.b,4,block.l,shape,out.baby);
        require(shape.n==8192&&shape.l==block.l&&shape.k==16,"selected record shape");
        out.shape=shape;out.tower=block.tower;out.coefficient=block.coefficient;out.ct=ct;out.baby_key=first.b.generic_string();out.mask=0;
        for(unsigned g=0;g<4;++g){
            const auto& job=jobs.at({block.tower,block.coefficient,ct,g});require(job.b==first.b,"baby must be shared across four groups");
            const auto key=job.a.generic_string();
            if(keys[g]!=key){
                auto words=std::make_shared<std::vector<uint64_t>>();InputCase ws;read_record(job.a,3,block.l,ws,*words);
                weights[g]=words;weight_shapes[g]=std::move(ws);keys[g]=key;
            }
            require(same_parameters(shape,weight_shapes[g]),"weight/baby parameters differ");
            out.weights[g]=weights[g];out.weight_keys[g]=key;out.expected[g]=hashes.at(job.gold.generic_string());
        }
    }
    const windowio::ReadStats& stats()const{return counters;}
    uint64_t network_bytes()const{return received_bytes;}
    double network_hash_ms()const{return received_hash_ms;}
};
} }
