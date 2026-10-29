#include "record_io.hpp"
#include <random>
static param_t parameter(uint64_t q){param_t p=q;ap_uint<129> u=ap_uint<129>(1)<<128;p.range(191,64)=ap_uint<128>(u/q);return p;}
static std::vector<word_t> model(const Record& in){
 hls::stream<axis_t> left,right,partials;
 check(ct_reader(in.words.data(),left,right,in.n,in.l,in.k)==OK,"reader status");
 const unsigned frames=in.l*(in.n/64)*in.k*4;
 for(unsigned f=0;f<frames;++f){uint16_t a[4][64],b[4][64];
  for(unsigned r=0;r<4;++r)for(unsigned j=0;j<64;j+=8){auto x=left.read(),y=right.read();for(unsigned lane=0;lane<8;++lane){a[r][j+lane]=x.range(16*lane+15,16*lane).to_uint();b[r][j+lane]=y.range(16*lane+15,16*lane).to_uint();}}
  for(unsigned d=0;d<7;++d)for(unsigned j=0;j<64;j+=4){axis_t beat=0;for(unsigned lane=0;lane<4;++lane){uint64_t s=0;for(unsigned r=0;r<4;++r)if(d>=r&&d-r<4)s+=uint64_t(a[r][j+lane])*b[d-r][j+lane];check(s<=0xffffffffULL,"diagonal overflow");beat.range(32*lane+31,32*lane)=uint32_t(s);}partials.write(beat);}
 }
 check(left.empty()&&right.empty(),"input streams not drained");std::vector<word_t> out(in.n*in.l*3,word_t(-1));
 check(ct_reduce_accum(partials,out.data(),in.params.data(),in.n,in.l,in.k)==OK,"reducer status");check(partials.empty(),"partials not drained");return out;
}
static std::vector<word_t> oracle(const Record& in){
 std::vector<word_t> out(in.n*in.l*3);using U=unsigned __int128;
 for(unsigned t=0;t<in.l;++t){uint64_t q=word_t(in.params[t].range(63,0)).to_uint64();for(unsigned j=0;j<in.n;++j){uint64_t sums[3]={};for(unsigned pair=0;pair<in.k;++pair){unsigned ix=((pair*in.l+t)*in.n+j)*4;U a=in.words[ix].to_uint64(),b=in.words[ix+1].to_uint64(),c=in.words[ix+2].to_uint64(),d=in.words[ix+3].to_uint64();sums[0]=(sums[0]+a*c)%q;sums[1]=(sums[1]+a*d+b*c)%q;sums[2]=(sums[2]+b*d)%q;}for(unsigned c=0;c<3;++c)out[(t*in.n+j)*3+c]=sums[c];}}
 return out;
}
static void same(const std::vector<word_t>& a,const std::vector<word_t>& b){check(a.size()==b.size(),"output count");for(size_t i=0;i<a.size();++i)check(a[i]==b[i],"residue mismatch at "+std::to_string(i));}
int main(int argc,char**argv){try{
 if(argc==3||argc==4){auto in=read_record(argv[1]);auto expected=read_record(argv[2]);check(in.kind==1&&expected.kind==2&&in.n==expected.n&&in.l==expected.l&&in.k==expected.k,"record shape mismatch");auto out=model(in);same(out,expected.words);if(argc==4)write_output(argv[3],in,out);std::cout<<"PASS REAL_RECORD_C_MODEL words="<<out.size()<<'\n';return 0;}
 std::mt19937_64 rng(280142);const uint64_t qs[]={(1ULL<<44)+1,(1ULL<<45)-1,(1ULL<<48)+1,(1ULL<<51)-129,(1ULL<<55)-55,(1ULL<<60)-1};
 unsigned cases=0;for(unsigned k:{1U,3U,16U})for(unsigned l:{1U,6U,16U}){Record in;in.kind=1;in.n=128;in.l=l;in.k=k;for(unsigned t=0;t<l;++t)in.params.push_back(parameter(qs[t%6]));for(unsigned pair=0;pair<k;++pair)for(unsigned t=0;t<l;++t)for(unsigned j=0;j<in.n;++j)for(unsigned c=0;c<4;++c){auto q=qs[t%6];unsigned code=(pair+t+j+c)%5;in.words.push_back(code==0?0:code==1?1:code==2?q-1:rng()%q);}same(model(in),oracle(in));++cases;std::cout<<"PASS REDUCER_C_MODEL N=128 L="<<l<<" K="<<k<<'\n';}
 hls::stream<axis_t> stream;word_t sentinel=123;param_t good=parameter(qs[0]);
 for(uint64_t q:std::array<uint64_t,4>{0,(1ULL<<44)-1,(1ULL<<60),(1ULL<<44)+2}){auto bad=parameter(q?q:1);check(ct_reduce_accum(stream,&sentinel,&bad,64,1,1)==BAD_PARAMETER,"invalid q accepted");}
 param_t bad=good+(param_t(1)<<64);check(ct_reduce_accum(stream,&sentinel,&bad,64,1,1)==BAD_PARAMETER,"invalid mu accepted");check(stream.empty()&&sentinel==123,"invalid parameter side effect");
 std::cout<<"PASS ALL_84BIT_REDUCER_C_MODELS cases="<<cases<<" plus bad parameters\n";return 0;
}catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
