#pragma once
namespace { namespace windowed {
struct Task {unsigned group,chunk;};
inline std::vector<Task> tasks(unsigned chunks,const std::string& layout,bool ascending){
 require(chunks>0&&(layout=="group"||layout=="chunk"),"window task layout");std::vector<Task> out;
 if(layout=="chunk")for(unsigned c=0;c<chunks;++c)for(unsigned x=0;x<6;++x)out.push_back({ascending?x:5-x,c});
 else for(unsigned x=0;x<6;++x)for(unsigned c=0;c<chunks;++c)out.push_back({ascending?x:5-x,c});
 return out;
}
inline bool bounded(const std::string& policy,bool exporting){require(policy=="retain"||policy=="bounded"||policy=="export_bounded","window cache policy");return policy=="bounded"||(policy=="export_bounded"&&exporting);}
inline std::pair<unsigned,unsigned> expected_cache_counts(const std::vector<Task>& jobs){unsigned loads=0,fills=0,last=UINT32_MAX;std::array<unsigned,2> bank{{UINT32_MAX,UINT32_MAX}};for(unsigned i=0;i<jobs.size();++i){auto c=jobs[i].chunk;if(c!=last){++loads;last=c;}if(c!=bank[i%2]){fills+=2;bank[i%2]=c;}}return {loads,fills};}
} }
