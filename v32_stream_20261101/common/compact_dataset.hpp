#pragma once
// Load ONE group. Shared baby rotations are stored once on disk, not duplicated
// six times or kept in a second448MiB resident input cache.
namespace {
InputCase read_operand(const fs::path& path,unsigned kind){
 require(kind==3||kind==4,"compact operand kind");std::ifstream f(path,std::ios::binary);require(bool(f),"missing compact operand");char magic[8]{};f.read(magic,8);require(std::string(magic,8)=="CKKSMAC1","compact magic");
 require(read_le(f,4)==1&&read_le(f,4)==kind,"compact version/kind");InputCase x;x.n=read_le(f,4);x.l=read_le(f,4);x.k=read_le(f,4);
 require(x.n>=128&&x.n<=8192&&is_power_of_two(x.n)&&x.l>=1&&x.l<=16&&x.k>=1&&x.k<=16,"compact shape bounds");
 for(unsigned v:std::array<unsigned,5>{2,1,64,0,0})require(read_le(f,4)==v,"compact layout");
 auto count=read_le(f,8);require(count==size_t(x.n)*x.l*x.k*2&&read_le(f,8)==0,"compact count/reserved");require(fs::file_size(path)==64+24ULL*x.l+8*count,"compact file length");
 for(unsigned t=0;t<x.l;++t){Parameter p;p.q=read_le(f,8);p.mu_lo=read_le(f,8);p.mu_hi=read_le(f,8);validate_parameter(p,t);x.parameters.push_back(p);}
 x.words.resize(count);read_words(f,x.words);require(f.peek()==EOF,"compact trailing bytes");
 // Avoid constructing a std::string (and heap allocation) for every valid word.
 // All coefficients remain checked; only the exceptional path formats an error.
 for(unsigned pair=0;pair<x.k;++pair)for(unsigned t=0;t<x.l;++t){const auto q=x.parameters[t].q;const auto base=(size_t(pair)*x.l+t)*x.n*2;for(size_t j=0;j<size_t(x.n)*2;++j)if(x.words[base+j]>=q)throw std::runtime_error("noncanonical compact operand at word "+std::to_string(base+j));}return x;
}
void load_compact_group(CachedDataset& dst,const fs::path& root,unsigned group){
 require(group<6,"group must be0..5");
 // Caller must finish ALL worker/backend accesses before releasing this cache.
 // Free old vectors before allocating the next group; never hold six datasets.
 dst.chunks.clear();dst.input_bytes=dst.golden_bytes=0;auto base=root/("group_"+std::to_string(group));
 std::ifstream sf(base/"shape.json");require(bool(sf)&&fs::file_size(base/"shape.json")<=16384,"compact shape file");std::string text((std::istreambuf_iterator<char>(sf)),{});
 unsigned full=shape_uint(text,"N"),l=shape_uint(text,"L"),k=shape_uint(text,"K"),n=shape_uint(text,"chunk_N"),count=shape_uint(text,"chunks");
 require(shape_uint(text,"group")==group&&full>=n&&full<=131072&&is_power_of_two(full)&&n>=128&&n<=8192&&is_power_of_two(n)&&full%n==0&&count==full/n&&count<=1024&&l>=1&&l<=16&&k>=1&&k<=16,"compact grid");
 std::ifstream mf(base/"chunks.tsv");std::string line;require(bool(std::getline(mf,line))&&line=="id\ttower_start\tcoefficient_start\tN\tL\tK","compact TSV header");dst.chunks.reserve(count);
 for(unsigned i=0;i<count;++i){require(bool(std::getline(mf,line)),"missing compact row");CachedChunk c;std::istringstream row(line);std::string extra;require(bool(row>>c.spec.id>>c.spec.tower_start>>c.spec.coefficient_start>>c.spec.n>>c.spec.l>>c.spec.k)&&!(row>>extra),"compact TSV row");require(c.spec.id=="chunk_"+std::to_string(i)&&c.spec.tower_start==0&&c.spec.coefficient_start==i*n&&c.spec.n==n&&c.spec.l==l&&c.spec.k==k,"compact coverage/order");
  auto a=read_operand(base/"chunks"/(c.spec.id+"_weight.bin"),3),b=read_operand(root/"shared"/(c.spec.id+"_baby.bin"),4);require(same_parameters(a,b)&&a.n==n&&a.l==l&&a.k==k,"compact pair parameter mismatch");
  c.input.n=n;c.input.l=l;c.input.k=k;c.input.parameters=a.parameters;c.input.words.resize(a.words.size()*2);
  for(size_t j=0;j<a.words.size()/2;++j){c.input.words[4*j]=a.words[2*j];c.input.words[4*j+1]=a.words[2*j+1];c.input.words[4*j+2]=b.words[2*j];c.input.words[4*j+3]=b.words[2*j+1];}
  c.expected=read_expected(base/"chunks"/(c.spec.id+"_expected.bin"),c.input);if(!dst.chunks.empty())require(same_parameters(dst.chunks.front().input,c.input),"nonuniform compact group");
  dst.input_bytes+=c.input.words.size()*8;dst.golden_bytes+=c.expected.size()*8;dst.chunks.push_back(std::move(c));
 }
 require(!std::getline(mf,line),"extra compact TSV rows");require(dst.golden_bytes==size_t(full)*l*3*8,"incomplete full group output");
}
}
