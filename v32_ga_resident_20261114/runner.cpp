#include <cstring>
#include <sys/resource.h>
#ifdef GA_RESIDENT_MODEL
#define CKKSMAC_PARSER_ONLY
#endif
#define FULL_HS4_BACKEND_ONLY
#include <variants/v32_native_pl_2_pipe/host/bo_host.cpp>
#undef FULL_HS4_BACKEND_ONLY
#include <common/finish_overlap.hpp>
#ifdef GA_RESIDENT_MODEL
#include <tests/mock_xrt.hpp>
#endif
#include "source.hpp"
#include "backend.hpp"

int main(int argc, char** argv) {
    using namespace ga_resident;
    try {
        ga::little_endian();
        if (argc == 2 && std::string(argv[1]) == "--crypto-check") {
            finishsha::Engine hash;
            std::cout << "PASS_GA_RESIDENT_SHA256 " << hash.description() << '\n';
            return 0;
        }
        check(argc == 9, "usage: runner XCLBIN MARKER DATA INDEX RESULTS ga6|ga9 smoke|full merge|direct");
        const auto setup_start = boexp::Clock::now();
        const path::path marker = argv[2], result = argv[5];
        const std::string name = argv[6], scope = argv[7], profile = argv[8];
        check(scope == "smoke" || scope == "full", "invalid scope");
        check(profile == "merge" || profile == "direct", "invalid profile");
        check(!path::exists(marker) && path::is_directory(result), "recovery marker or result directory");
        const auto layer = layer_for(name);
        uint64_t bytes = 0;
        auto windows = schedule(layer, bytes);
        finishsha::Engine hash;
        Source source(argv[3], argv[4], hash, bytes, layer.tiles());
#ifdef GA_RESIDENT_MODEL
        xrt::device device;
        xrt::uuid uuid;
        const char* backend_name = "xrt_contract_model";
        xrt::corrupt_output = std::getenv("GA_RESIDENT_TEST_CORRUPT_OUTPUT") != nullptr;
        xrt::corrupt_input_sync = std::getenv("GA_RESIDENT_TEST_CORRUPT_INPUT_SYNC") != nullptr;
#else
        validate_boot_xclbin(argv[1]);
        validate_boot_marker();
        xrt::ini::set("Runtime.enable_flat", "false");
        xrt::ini::set("Runtime.force_program_xclbin", "false");
        xrt::ini::set("Runtime.ert_polling", "true");
        xrt::ini::set("Runtime.xgq_polling", "true");
        auto device = xrt::device(0);
        auto uuid = device.load_xclbin(argv[1]);
        const char* backend_name = "pure_pl";
#endif
        Backend backend(device, uuid, layer.groups, hash, source, profile == "direct");
        boexp::Worker worker;
        std::ofstream tiles(result / "tiles.csv"), timing(result / "windows.csv");
        check(bool(tiles) && bool(timing), "cannot open result CSV");
        tiles << "tile,block,output,group,L,sha256,weight_copy_sync_ms,baby_copy_sync_ms,"
                 "prepare_lane_ms,execute_ms,status_ms,output_sync_ms,merge_copy_ms,output_sha256_ms\n";
        timing << "block,output,L,admission_ms,resident_ms\n" << std::setprecision(12);
        tiles << std::setprecision(12);
        const double setup_ms = boexp::elapsed(setup_start, boexp::Clock::now());
        const auto request_start = boexp::Clock::now();
        uint64_t verified_words = 0, uploaded_bytes = 0;
        unsigned checked_tiles = 0, checked_windows = 0;
        double resident_ms = 0, admission_ms = 0;
        const Tile* current_shape = nullptr;
        for (auto& window : windows) {
            if (scope == "smoke" && window.block != 0 && window.block != layer.blocks() - 1) continue;
            const auto admission_start = boexp::Clock::now();
            source.admit(window);
            if (window.output == 0) current_shape = &window.tiles.front();
            check(current_shape && window.tiles.front().same_shape(*current_shape),
                  "reused weights have a different shape");
            const double admitted = boexp::elapsed(admission_start, boexp::Clock::now());
            admission_ms += admitted;
            {
                std::ofstream active(marker);
                active << "PL window " << window.block << '/' << window.output << '\n';
                active.close();
                check(bool(active), "cannot write recovery marker");
            }
            const auto resident_start = boexp::Clock::now();
            backend.configure(window);
            const auto run = boexp::run_finish_overlap(backend, layer.groups, worker, false);
            const auto verified_ms = boexp::elapsed(resident_start, boexp::Clock::now());
            check(path::remove(marker), "cannot remove recovery marker");
            resident_ms += verified_ms;
            ++checked_windows;
            timing << window.block << ',' << window.output << ',' << window.tiles.front().l << ','
                   << admitted << ',' << verified_ms << '\n';
            for (unsigned i = 0; i < window.tiles.size(); ++i) {
                const auto& tile = window.tiles[i];
                const auto& frame = run.frames[i];
                verified_words += tile.output_words();
                uploaded_bytes += tile.input_words() * 8 *
                    (2 - bool(tile.flags & ga::reuse_weight) - bool(tile.flags & ga::reuse_baby));
                ++checked_tiles;
                tiles << tile.id << ',' << window.block << ',' << window.output << ',' << tile.slot
                      << ',' << tile.l << ',' << backend.digests[i];
                for (const char* stage : {"weight_copy_sync", "baby_copy_sync", "prepare_lane", "execute",
                                          "status", "output_sync", "merge_copy", "output_sha256"}) {
                    tiles << ',' << frame.total(stage);
                }
                tiles << '\n';
            }
            if (checked_tiles % (layer.groups * 32) == 0 || window.output + 1 == layer.outputs) {
                timing.flush();
                tiles.flush();
                check(bool(timing) && bool(tiles), "cannot persist progress");
            }
            if (checked_windows % 32 == 0) {
                std::cout << "GA_RESIDENT_PROGRESS " << name << " windows=" << checked_windows
                          << '/' << windows.size() << " tiles=" << checked_tiles << std::endl;
            }
        }
        source.check_end();
        check(checked_tiles == (scope == "full" ? layer.tiles() : 2 * layer.outputs * layer.groups),
              "tile coverage differs");
        check(uploaded_bytes == source.admitted_payload_bytes, "BO upload coverage differs");
        if (scope == "full") {
            check(verified_words == layer.words() && source.part_read_bytes == bytes,
                  "full replay coverage differs");
        }
        const double request_ms = boexp::elapsed(request_start, boexp::Clock::now());
        timing.close();
        tiles.close();
        check(bool(timing) && bool(tiles), "cannot close result CSV");
        struct rusage usage{};
        check(::getrusage(RUSAGE_SELF, &usage) == 0, "cannot collect process resource statistics");
        std::ofstream summary(result / "native.json");
        summary << std::setprecision(12)
                << "{\n  \"backend\": \"" << backend_name << "\",\n"
                << "  \"windows\": " << checked_windows << ",\n"
                << "  \"tiles\": " << checked_tiles << ",\n"
                << "  \"verified_words\": " << verified_words << ",\n"
                << "  \"uploaded_bytes\": " << uploaded_bytes << ",\n"
                << "  \"verified_parts\": " << source.parts_read << ",\n"
                << "  \"part_read_bytes\": " << source.part_read_bytes << ",\n"
                << "  \"part_retirement_advice_failures\": " << source.retire_failures << ",\n"
                << "  \"peak_process_rss_kib\": " << usage.ru_maxrss << ",\n"
                << "  \"part_read_ms\": " << source.read_ms << ",\n"
                << "  \"input_sha256_ms\": " << source.hash_ms << ",\n"
                << "  \"setup_ms\": " << setup_ms << ",\n"
                << "  \"admission_ms\": " << admission_ms << ",\n"
                << "  \"resident_ms\": " << resident_ms << ",\n"
                << "  \"request_ms\": " << request_ms << "\n}\n";
        summary.close();
        check(bool(summary), "cannot write result summary");
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "GA_RESIDENT_FAIL: " << error.what() << '\n';
        return 1;
    }
}
