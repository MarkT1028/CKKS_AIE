// Standalone CPU-only cache utility. Reuses the strict canonical input parser;
// WINDOW_SOFTWARE_MODEL excludes XRT, graph construction and device access.
#define WINDOW_SOFTWARE_MODEL
#define GA3_IO_PROFILE 2
#define GA3_CACHE_TOOL
#include "../host/ga3_host.cpp"
#include "../common/packed_input.hpp"

int main(int argc,char**argv){try{
 require(argc==5,"compact_tool prepare|verify ORIGINAL PACKED EXPECTED_SHA256");
 const std::string action=argv[1],expected=argv[4];require(action=="prepare"||action=="verify","compact action");
 auto begin=Clock::now();const fs::path original=argv[2],path=argv[3];
 // Kind is read only from the original header and then checked by Record.
 std::ifstream f(original,std::ios::binary);std::array<uint8_t,16> p{};f.read(reinterpret_cast<char*>(p.data()),p.size());require(bool(f),"original header read");
 windowio::Record r(original,unsigned(windowio::little(p.data()+12,4)));const auto header=windowio::input_header(r);sealedsha::Engine engine;
 if(action=="prepare"){
  require(!fs::exists(path)&&!fs::is_symlink(path),"refuse to overwrite packed cache");
  auto raw=r.read_canonical();require(engine.hex(header.data(),header.size(),raw.data(),raw.size()*8)==expected,"original input SHA256 mismatch");
  std::vector<uint8_t> packed(windowio::packed_bytes(r)+8,0);size_t offset=0,index=0;const size_t count=size_t(r.shape.n)*2;
  for(unsigned k=0;k<r.shape.k;++k)for(const auto&a:r.shape.parameters){compactbits::encode(raw.data()+index,count,a.q,packed.data()+offset);index+=count;offset+=compactbits::bytes(count,compactbits::width(a.q));}
  std::vector<uint64_t> decoded;windowio::decode_payload(r,packed.data(),decoded);require(decoded==raw,"pre-write packed roundtrip differs");
  windowio::Fd fd;fd.value=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);require(fd.value>=0,"new packed file create");
  auto write=[&](const uint8_t*src,size_t n){size_t done=0;while(done<n){auto got=::write(fd.value,src+done,n-done);if(got<0&&errno==EINTR)continue;require(got>0,"packed write");done+=size_t(got);}};
  auto h=windowio::wrapper(r,expected);write(h.data(),h.size());write(packed.data(),offset);require(::fsync(fd.value)==0,"packed fsync");
  // Read the actual new file back, decode, and verify the ORIGINAL full
  // canonical digest. Cost is part of cache preparation, never hidden.
 }
 std::vector<uint64_t> restored;std::vector<uint8_t> scratch;windowio::read_packed(path,r,expected,restored,scratch);
 require(engine.hex(header.data(),header.size(),restored.data(),restored.size()*8)==expected,"read-back expanded canonical SHA256 mismatch");
 const auto wh=windowio::wrapper(r,expected);const auto packed_sha=engine.hex(wh.data(),wh.size(),scratch.data(),windowio::packed_bytes(r));
 r.retire();std::cout<<std::setprecision(12)<<"{\"status\":\"PASS_LOSSLESS_INPUT_CACHE\",\"logical_bytes\":"<<r.words*8
 <<",\"packed_bytes\":"<<fs::file_size(path)<<",\"packed_sha256\":\""<<packed_sha<<"\",\"canonical_sha256\":\""<<expected<<"\",\"wall_ms\":"<<ms(begin,Clock::now())<<"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
