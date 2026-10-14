// Reuse the exact parser, boot-only preflight and output writer from the
// validated timing host. This follows the existing CPU benchmark convention.
#define main ckks_original_timing_main
#include "ckks_mac_timed_xrt.cpp"
#undef main
#include <algorithm>
#include <cmath>
#include <memory>
#ifndef CKKSMAC_PARSER_ONLY
#if __has_include(<xrt/xrt_aie.h>)
#include <xrt/xrt_aie.h>
#define CKKS_HAS_PLIO_PROFILE 1
#elif __has_include(<experimental/xrt_aie.h>)
#include <experimental/xrt_aie.h>
#define CKKS_HAS_PLIO_PROFILE 1
#else
#define CKKS_HAS_PLIO_PROFILE 0
#endif
#endif

namespace {
using Clock = std::chrono::steady_clock;
double elapsed_ms(Clock::time_point begin, Clock::time_point end) {
    return std::chrono::duration<double, std::milli>(end - begin).count();
}
int64_t unix_us_now() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::system_clock::now().time_since_epoch()).count();
}
unsigned count_arg(const std::string& text, unsigned lo, unsigned hi) {
    require(!text.empty() && text.find_first_not_of("0123456789") == std::string::npos,
            "repetition count must be an unsigned integer");
    size_t used = 0;
    const auto n = std::stoull(text, &used);
    require(used == text.size() && n >= lo && n <= hi,
            "repetition count outside allowed range");
    return static_cast<unsigned>(n);
}
std::vector<uint64_t> read_expected(const fs::path& path, const InputCase& input) {
    require(fs::file_size(path) == 64 + input.parameters.size() * 24 +
                                     input.output_words() * 8,
            "expected output length mismatch");
    std::ifstream f(path, std::ios::binary);
    require(bool(f), "cannot open expected output");
    char magic[8]{};
    f.read(magic, 8);
    require(std::string(magic, 8) == "CKKSMAC1", "expected output magic mismatch");
    for (const uint32_t v : std::array<uint32_t, 10>{
            1, 2, input.n, input.l, input.k, 3, 1, 64, 0, 0})
        require(read_le(f, 4) == v, "expected output header mismatch");
    require(read_le(f, 8) == input.output_words(), "expected output word count mismatch");
    require(read_le(f, 8) == 0, "expected output reserved field mismatch");
    for (const auto& p : input.parameters) {
        require(read_le(f, 8) == p.q, "expected modulus mismatch");
        require(read_le(f, 8) == p.mu_lo, "expected reciprocal mismatch");
        require(read_le(f, 8) == p.mu_hi, "expected reciprocal mismatch");
    }
    std::vector<uint64_t> words(static_cast<size_t>(input.output_words()));
    for (size_t i = 0; i < words.size(); ++i) {
        words[i] = read_le(f, 8);
        const auto t = i / (size_t(input.n) * 3);
        require(words[i] < input.parameters[t].q,
                "noncanonical expected residue at word " + std::to_string(i));
    }
    require(f.peek() == EOF, "unexpected bytes after expected output");
    return words;
}
double median(std::vector<double> v) {
    require(!v.empty(), "no measured samples");
    std::sort(v.begin(), v.end());
    const size_t n = v.size();
    return n % 2 ? v[n / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
}
double p95(std::vector<double> v) {
    require(!v.empty(), "no measured samples");
    std::sort(v.begin(), v.end());
    return v[static_cast<size_t>(std::ceil(v.size() * .95)) - 1];
}

#ifndef CKKSMAC_PARSER_ONLY
void persistent_run(const fs::path& xclbin, const InputCase& input,
                    const std::vector<uint64_t>& golden, const fs::path& dir,
                    const std::string& mode, unsigned repetitions,
                    unsigned warmups, uint64_t timeout_ms,
                    const std::string& profile_port) {
    require(mode == "resident" || mode == "transfer", "mode must be resident or transfer");
    require(profile_port == "none" || profile_port == "left" ||
            profile_port == "right" || profile_port == "partials", "invalid counter port");
    require(!fs::exists(dir), "result directory already exists; choose a new path");
    require(input.frames() <= static_cast<uint64_t>(std::numeric_limits<int>::max()),
            "graph iteration count exceeds API range");
    fs::create_directories(dir);
    std::ofstream csv(dir / "iterations.csv");
    require(bool(csv), "cannot create iteration CSV");
    csv << "repetition,warmup,upload_ms,poison_ms,counter_setup_ms,launch_ms,"
           "reader_observed_done_ms,reducer_observed_done_ms,graph_observed_done_ms,"
           "execution_ms,status_ms,readback_ms,validation_ms,transaction_ms,"
           "counter_cycles,counter_bytes,execution_start_session_ms,"
           "execution_end_session_ms,execution_start_unix_us,execution_end_unix_us\n";
    csv << std::fixed << std::setprecision(6);
    std::cout << std::fixed << std::setprecision(6);

    const auto init_begin = Clock::now();
    validate_boot_xclbin(xclbin);
    validate_boot_marker();
    xrt::ini::set("Runtime.enable_flat", "false");
    xrt::ini::set("Runtime.force_program_xclbin", "false");
    xrt::ini::set("Runtime.ert_polling", "true");
    xrt::ini::set("Runtime.xgq_polling", "true");
    std::cout << "STAGE one metadata registration; boot hardware is reused\n" << std::flush;
    auto device = xrt::device(0);
    const auto uuid = device.load_xclbin(xclbin.string());
    auto reader = xrt::kernel(device, uuid, "ct_reader:{ct_reader_1}",
                              xrt::kernel::cu_access_mode::exclusive);
    auto reducer = xrt::kernel(device, uuid, "ct_reduce_accum:{ct_reduce_accum_1}",
                               xrt::kernel::cu_access_mode::exclusive);
    auto graph = xrt::graph(device, uuid, "ckks_graph");
    const auto init_end = Clock::now();

    const auto parameters = pack_parameters(input);
    std::vector<uint64_t> output(golden.size());
    const size_t input_bytes = input.words.size() * sizeof(uint64_t);
    const size_t parameter_bytes = parameters.size() * sizeof(uint64_t);
    const size_t output_bytes = output.size() * sizeof(uint64_t);
    auto input_bo = xrt::bo(device, input_bytes, reader.group_id(0));
    auto output_bo = xrt::bo(device, output_bytes, reducer.group_id(1));
    auto parameter_bo = xrt::bo(device, parameter_bytes, reducer.group_id(2));
    const auto allocate_end = Clock::now();
    input_bo.write(input.words.data(), input_bytes, 0);
    parameter_bo.write(parameters.data(), parameter_bytes, 0);
    input_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    parameter_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    const auto upload_end = Clock::now();
    xrt::run reader_run(reader), reducer_run(reducer);
    reducer_run.set_arg(1, output_bo);
    reducer_run.set_arg(2, parameter_bo);
    reducer_run.set_arg(3, input.n);
    reducer_run.set_arg(4, input.l);
    reducer_run.set_arg(5, input.k);
    reader_run.set_arg(0, input_bo);
    reader_run.set_arg(3, input.n);
    reader_run.set_arg(4, input.l);
    reader_run.set_arg(5, input.k);
    graph.reset(); // Once for this session, never between successful repetitions.
    const auto setup_end = Clock::now();

    std::string port_name;
    uint64_t port_bytes = 0;
    if (profile_port != "none") {
        port_name = "ckks_graph." + profile_port;
        port_bytes = checked_mul(input.frames(), profile_port == "partials" ? 4096 : 512,
                                 "profile bytes");
        require(port_bytes <= std::numeric_limits<uint32_t>::max(),
                "profile transfer count exceeds 32-bit event API");
#if !CKKS_HAS_PLIO_PROFILE
        throw std::runtime_error("XRT AIE profiling header is unavailable; use runtime profile configs instead");
#endif
    }
    std::cout << "SESSION mode=" << mode << " K=" << input.k
              << " repetitions=" << repetitions << " warmups=" << warmups
              << " counter_port=" << profile_port
              << " init_ms=" << elapsed_ms(init_begin, init_end)
              << " allocate_ms=" << elapsed_ms(init_end, allocate_end)
              << " initial_upload_ms=" << elapsed_ms(allocate_end, upload_end)
              << " setup_ms=" << elapsed_ms(upload_end, setup_end) << "\n" << std::flush;

    std::vector<double> executions, transactions;
    auto measured_begin = Clock::now();
    for (unsigned repetition = 0; repetition < warmups + repetitions; ++repetition) {
        if (repetition == warmups) measured_begin = Clock::now();
        const auto begin = Clock::now();
        if (mode == "transfer") {
            input_bo.write(input.words.data(), input_bytes, 0);
            parameter_bo.write(parameters.data(), parameter_bytes, 0);
            input_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
            parameter_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
        }
        const auto repeated_upload_end = Clock::now();
        // Poison every output so a repeated test cannot pass using stale DDR data.
        std::fill(output.begin(), output.end(), std::numeric_limits<uint64_t>::max());
        output_bo.write(output.data(), output_bytes, 0);
        output_bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
        const auto poison_end = Clock::now();
#if CKKS_HAS_PLIO_PROFILE
        std::unique_ptr<xrt::aie::profiling> event;
        if (!port_name.empty()) {
            event = std::make_unique<xrt::aie::profiling>(device);
            const int handle = event->start(
                xrt::aie::profiling::profiling_option::io_stream_start_to_bytes_transferred_cycles,
                port_name, "", static_cast<uint32_t>(port_bytes));
            require(handle >= 0, "PLIO counter allocation failed for " + port_name);
        }
#endif
        const auto execution_begin = Clock::now();
        const auto execution_start_unix_us = unix_us_now();
        auto launch_end = execution_begin, reader_end = execution_begin;
        auto reducer_end = execution_begin, graph_end = execution_begin;
        uint64_t cycles = 0;
        int64_t execution_end_unix_us = 0;
        try {
            reducer_run.start();
            graph.run(static_cast<int>(input.frames()));
            reader_run.start();
            launch_end = Clock::now();
            const auto deadline = execution_begin + std::chrono::milliseconds(timeout_ms);
            wait_for_run("ct_reader", reader_run, deadline);
            reader_end = Clock::now();
            wait_for_run("ct_reduce_accum", reducer_run, deadline);
            reducer_end = Clock::now();
            graph.wait(remaining_time(deadline));
            graph_end = Clock::now();
            execution_end_unix_us = unix_us_now();
#if CKKS_HAS_PLIO_PROFILE
            if (event) {
                cycles = event->read();
                event->stop();
                event.reset();
                require(cycles > 0, "PLIO counter returned zero; no valid profile result");
            }
#endif
        } catch (...) {
#if CKKS_HAS_PLIO_PROFILE
            if (event) { try { event->stop(); } catch (...) {} }
#endif
            try { reader_run.abort(); } catch (...) {}
            try { reducer_run.abort(); } catch (...) {}
            try { graph.reset(); } catch (...) {}
            throw; // Never continue a session after an incomplete transaction.
        }
        const auto status_begin = Clock::now();
        require(reader.read_register(0x10) == 0, "ct_reader returned an error");
        require(reducer.read_register(0x10) == 0, "ct_reduce_accum returned an error");
        const auto status_end = Clock::now();
        output_bo.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
        output_bo.read(output.data(), output_bytes, 0);
        const auto readback_end = Clock::now();
        for (size_t i = 0; i < output.size(); ++i)
            require(output[i] == golden[i], "hardware mismatch at repetition " +
                    std::to_string(repetition) + " word " + std::to_string(i));
        const auto end = Clock::now();
        const double execution = elapsed_ms(execution_begin, graph_end);
        const double transaction = elapsed_ms(begin, end);
        const bool warmup = repetition < warmups;
        if (!warmup) { executions.push_back(execution); transactions.push_back(transaction); }
        csv << repetition << ',' << warmup << ','
            << elapsed_ms(begin, repeated_upload_end) << ','
            << elapsed_ms(repeated_upload_end, poison_end) << ','
            << elapsed_ms(poison_end, execution_begin) << ','
            << elapsed_ms(execution_begin, launch_end) << ','
            << elapsed_ms(execution_begin, reader_end) << ','
            << elapsed_ms(execution_begin, reducer_end) << ','
            << elapsed_ms(execution_begin, graph_end) << ',' << execution << ','
            << elapsed_ms(status_begin, status_end) << ','
            << elapsed_ms(status_end, readback_end) << ','
            << elapsed_ms(readback_end, end) << ',' << transaction << ',';
        if (!port_name.empty()) csv << cycles;
        csv << ',';
        if (!port_name.empty()) csv << port_bytes;
        csv << ',' << elapsed_ms(init_begin, execution_begin)
            << ',' << elapsed_ms(init_begin, graph_end)
            << ',' << execution_start_unix_us << ',' << execution_end_unix_us << '\n';
        require(bool(csv), "failed to write iteration CSV");
        if (warmup || (repetition - warmups + 1) % 10 == 0 || repetition + 1 == warmups + repetitions)
            std::cout << "PASS repetition=" << repetition << " warmup=" << warmup
                      << " execution_ms=" << execution << " transaction_ms=" << transaction
                      << " verified_words=" << output.size() << "\n" << std::flush;
    }
    const auto measured_end = Clock::now();
    csv.close();
    require(bool(csv), "failed to finalize iteration CSV");
    write_output(dir / "output_last.bin", input, output);
    std::ofstream summary(dir / "summary.csv");
    require(bool(summary), "cannot create summary CSV");
    summary << "K,mode,repetitions,warmups,init_ms,allocate_ms,initial_upload_ms,setup_ms,"
               "execution_median_ms,execution_p95_ms,execution_min_ms,execution_max_ms,"
               "transaction_median_ms,transaction_p95_ms,measured_loop_wall_ms,counter_port\n"
            << std::fixed << std::setprecision(6)
            << input.k << ',' << mode << ',' << repetitions << ',' << warmups << ','
            << elapsed_ms(init_begin, init_end) << ',' << elapsed_ms(init_end, allocate_end) << ','
            << elapsed_ms(allocate_end, upload_end) << ',' << elapsed_ms(upload_end, setup_end) << ','
            << median(executions) << ',' << p95(executions) << ','
            << *std::min_element(executions.begin(), executions.end()) << ','
            << *std::max_element(executions.begin(), executions.end()) << ','
            << median(transactions) << ',' << p95(transactions) << ','
            << elapsed_ms(measured_begin, measured_end) << ',' << profile_port << '\n';
    summary.close();
    require(bool(summary), "failed to finalize summary CSV");
    std::cout << "PERSISTENT_MEDIAN execution_ms=" << median(executions)
              << " transaction_ms=" << median(transactions) << "\n"
              << "PASS PERSISTENT: every repetition matched the full expected payload\n"
              << "RESULTS=" << dir.string() << "\n";
}
#endif
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 3 && std::string(argv[1]) == "--inspect-xclbin") {
            validate_boot_xclbin(argv[2]); return 0;
        }
        if (argc == 4 && std::string(argv[1]) == "--inspect-case") {
            const auto input = read_input(argv[2]);
            const auto golden = read_expected(argv[3], input);
            print_inspection(input);
            std::cout << "PASS expected header and canonical payload words=" << golden.size() << '\n';
            return 0;
        }
        if (argc == 2 && std::string(argv[1]) == "--capabilities") {
#ifndef CKKSMAC_PARSER_ONLY
            std::cout << "PLIO_COUNTER_API=" << CKKS_HAS_PLIO_PROFILE << '\n';
#else
            std::cout << "PARSER_ONLY=1\n";
#endif
            return 0;
        }
#ifdef CKKSMAC_PARSER_ONLY
        throw std::runtime_error("parser-only build accepts --inspect-case / --inspect-xclbin");
#else
        require(argc >= 8 && argc <= 10,
                "Usage: ckks_mac_persistent_xrt XCLBIN INPUT EXPECTED OUTDIR "
                "resident|transfer REPETITIONS WARMUPS [TIMEOUT_MS] [none|left|right|partials]");
        const auto input = read_input(argv[2]);
        const auto golden = read_expected(argv[3], input);
        print_inspection(input);
        persistent_run(argv[1], input, golden, argv[4], argv[5],
                       count_arg(argv[6], 1, 10000), count_arg(argv[7], 0, 100),
                       argc >= 9 ? parse_timeout(argv[8]) : 120000,
                       argc == 10 ? argv[9] : "none");
        return 0;
#endif
    } catch (const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << '\n'; return 1;
    }
}
