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
    read_words(f,words);
    for(size_t t=0;t<input.l;++t){const auto q=input.parameters[t].q;
        const size_t begin=t*size_t(input.n)*3;
        for(size_t j=0;j<size_t(input.n)*3;++j)
            if(words[begin+j]>=q)
                throw std::runtime_error("noncanonical expected residue at word "+std::to_string(begin+j));
    }
    require(f.peek() == EOF, "unexpected bytes after expected output");
    return words;
}
