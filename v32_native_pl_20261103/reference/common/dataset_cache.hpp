#pragma once
#include <algorithm>
#include <regex>
#include <utility>

// InputCase/read_input/read_expected are supplied by the unchanged release
// parser before this header. All cached payloads are ordinary host RAM, not BOs.
namespace {
struct CachedSpec {
    std::string id;
    unsigned tower_start=0,coefficient_start=0,n=0,l=0,k=0;
};
struct CachedChunk {
    CachedSpec spec;
    InputCase input;
    std::vector<uint64_t> expected;
};
unsigned shape_uint(const std::string& json,const std::string& key) {
    const std::regex expression("\\\""+key+"\\\"\\s*:\\s*([0-9]+)(?=\\s*[,}])");
    auto first=std::sregex_iterator(json.begin(),json.end(),expression),end=std::sregex_iterator();
    require(first!=end,"missing unsigned shape field: "+key);
    auto value=std::stoull((*first)[1].str());
    require(++first==end&&value<=131072,"duplicate or oversized shape field: "+key);
    return static_cast<unsigned>(value);
}
std::vector<CachedSpec> cached_specs(const fs::path& root) {
    std::ifstream info(root/"shape.json");require(bool(info),"shape.json missing");
    require(fs::file_size(root/"shape.json")<=16384,"oversized shape.json");
    const std::string json((std::istreambuf_iterator<char>(info)),{});
    const unsigned full_n=shape_uint(json,"N"),l=shape_uint(json,"L"),k=shape_uint(json,"K"),count=shape_uint(json,"chunks");
    require(full_n>=128&&full_n<=131072&&(full_n&(full_n-1))==0,"full N out of range");
    require(l>=1&&l<=16&&k>=1&&k<=16&&count>=1&&count<=16,"cached replay supports one uniform tower group and <=16 chunks");
    const unsigned n=std::min(8192U,full_n);
    require(count==full_n/n,"incomplete cached chunk coverage");
    std::ifstream manifest(root/"chunks.tsv");require(bool(manifest),"chunks.tsv missing");
    std::string line;std::getline(manifest,line);
    require(line=="id\ttower_start\tcoefficient_start\tN\tL\tK","invalid cached manifest header");
    std::vector<CachedSpec> out;out.reserve(count);
    while(std::getline(manifest,line)) {
        CachedSpec s;std::istringstream row(line);
        require(bool(row>>s.id>>s.tower_start>>s.coefficient_start>>s.n>>s.l>>s.k),"invalid cached manifest row");
        std::string extra;require(!(row>>extra),"extra cached manifest fields");
        require(out.size()<count&&s.id=="chunk_"+std::to_string(out.size()),"duplicate or noncanonical chunk id");
        require(s.tower_start==0&&s.coefficient_start==out.size()*n&&s.n==n&&s.l==l&&s.k==k,"cached grid mismatch");
        out.push_back(s);
    }
    require(out.size()==count,"missing cached manifest rows");
    return out;
}
bool same_parameters(const InputCase& a,const InputCase& b) {
    if(a.n!=b.n||a.l!=b.l||a.k!=b.k||a.parameters.size()!=b.parameters.size())return false;
    for(size_t i=0;i<a.parameters.size();++i) {
        const auto& x=a.parameters[i];const auto& y=b.parameters[i];
        if(x.q!=y.q||x.mu_lo!=y.mu_lo||x.mu_hi!=y.mu_hi)return false;
    }
    return true;
}
struct CachedDataset {
    std::vector<CachedChunk> chunks;
    uint64_t input_bytes=0,golden_bytes=0;
    CachedDataset()=default; // New full-layer runner admits one compact group at a time.
    explicit CachedDataset(const fs::path& root) {
        const auto specs=cached_specs(root);chunks.reserve(specs.size());
        for(const auto& s:specs) {
            CachedChunk c;c.spec=s;c.input=read_input(root/"chunks"/(s.id+"_input.bin"));
            require(c.input.n==s.n&&c.input.l==s.l&&c.input.k==s.k,"cached input/header mismatch");
            c.expected=read_expected(root/"chunks"/(s.id+"_expected.bin"),c.input);
            if(!chunks.empty())require(same_parameters(chunks.front().input,c.input),"nonuniform cached parameters");
            input_bytes+=c.input.words.size()*sizeof(uint64_t);
            golden_bytes+=c.expected.size()*sizeof(uint64_t);
            chunks.emplace_back(std::move(c));
        }
    }
};

// A fixed ComputePool already references holder. Borrow a cached vector with
// O(1) swaps, wait for ALL workers, and restore before the next chunk. Never
// deep-copy 56 MiB of input just to point the unchanged CPU core at a chunk.
class CachedInputLease {
    InputCase& holder;
    InputCase& cached;
    bool active=true;
public:
    CachedInputLease(InputCase& destination,InputCase& source):holder(destination),cached(source) {
        require(&holder!=&cached&&holder.words.empty()&&holder.parameters.empty(),"cache lease requires empty holder");
        using std::swap;swap(holder,cached);
    }
    CachedInputLease(const CachedInputLease&)=delete;
    CachedInputLease& operator=(const CachedInputLease&)=delete;
    void restore() noexcept {if(active){using std::swap;swap(holder,cached);active=false;}}
    ~CachedInputLease(){restore();}
};

void fill_shard_block(const InputCase& in,unsigned lane,InputCase& out) {
    require(&in!=&out&&lane<2&&in.n>=128&&in.n<=8192&&(in.n&(in.n-1))==0,"invalid block split");
    require(in.l>=1&&in.l<=16&&in.k>=1&&in.k<=16&&in.parameters.size()==in.l,"invalid block shape");
    require(in.words.size()==size_t(in.n)*in.l*in.k*4,"block input length mismatch");
    out.n=in.n/2;out.l=in.l;out.k=in.k;out.parameters=in.parameters;
    out.words.resize(in.words.size()/2);
    const size_t words_per_lane=size_t(out.n)*4;
    for(unsigned pair=0;pair<in.k;++pair)for(unsigned t=0;t<in.l;++t) {
        const size_t index=size_t(pair)*in.l+t;
        const size_t source=(index*in.n+lane*out.n)*4;
        std::copy_n(in.words.data()+source,words_per_lane,out.words.data()+index*words_per_lane);
    }
}
}
