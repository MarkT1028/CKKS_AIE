#pragma once
#include <sys/resource.h>
#include <map>
namespace { namespace streamio {
struct Metrics {
 uint64_t rchar=0,read_bytes=0,write_bytes=0;long minor_faults=0,major_faults=0;uint64_t rss_kib=0,anon_kib=0,file_kib=0,highwater_kib=0;
 static Metrics now(){
  Metrics m;std::ifstream io("/proc/self/io");std::string key;uint64_t v;while(io>>key>>v){if(key=="rchar:")m.rchar=v;if(key=="read_bytes:")m.read_bytes=v;if(key=="write_bytes:")m.write_bytes=v;}
  std::ifstream status("/proc/self/status");std::string line;while(std::getline(status,line)){std::istringstream s(line);s>>key>>v;if(key=="VmRSS:")m.rss_kib=v;if(key=="RssAnon:")m.anon_kib=v;if(key=="RssFile:")m.file_kib=v;if(key=="VmHWM:")m.highwater_kib=v;}
  struct rusage r{};require(::getrusage(RUSAGE_SELF,&r)==0,"getrusage failed");m.minor_faults=r.ru_minflt;m.major_faults=r.ru_majflt;return m;
 }
 std::string delta_json(const Metrics& a)const{std::ostringstream s;s<<"{\"read_bytes\":"<<(read_bytes-a.read_bytes)<<",\"rchar\":"<<(rchar-a.rchar)<<",\"write_bytes\":"<<(write_bytes-a.write_bytes)<<",\"minor_faults\":"<<(minor_faults-a.minor_faults)<<",\"major_faults\":"<<(major_faults-a.major_faults)<<",\"VmRSS_kib\":"<<rss_kib<<",\"RssAnon_kib\":"<<anon_kib<<",\"RssFile_kib\":"<<file_kib<<",\"VmHWM_kib\":"<<highwater_kib<<"}";return s.str();}
};
} }
