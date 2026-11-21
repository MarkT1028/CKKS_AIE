using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

public static class V32GaSender
{
    private static readonly Dictionary<string, Regex> Format = new Dictionary<string, Regex> {
        { "ga0", new Regex(@"\Adata/[ap]_\d{2}_\d{2}_\d{2}\.bin\z", RegexOptions.CultureInvariant) },
        { "ga3", new Regex(@"\A(?:weights|baby)/[a-zA-Z0-9_]+\.bin\z", RegexOptions.CultureInvariant) },
        { "ga3cache", new Regex(@"\Ainputs/[0-9a-f]{64}\.qpk\z", RegexOptions.CultureInvariant) },
        { "ga6", new Regex(@"\Aparts/batch_\d{2}/part_\d{4}\.part\z", RegexOptions.CultureInvariant) },
        { "ga9", new Regex(@"\Aparts/batch_\d{2}/part_\d{4}\.part\z", RegexOptions.CultureInvariant) }
    };

    public static string NewKey()
    {
        byte[] random = new byte[32];
        using (RandomNumberGenerator rng = RandomNumberGenerator.Create()) rng.GetBytes(random);
        return BitConverter.ToString(random).Replace("-", "").ToLowerInvariant();
    }

    private static string ReadLine(Stream stream)
    {
        byte[] line = new byte[256];
        for (int i = 0; i < line.Length; i++) {
            int value = stream.ReadByte();
            if (value == -1 && i == 0) return null;
            if (value == '\n') return Encoding.ASCII.GetString(line, 0, i);
            if (value < 32 || value > 126) throw new InvalidDataException("Invalid request");
            line[i] = (byte)value;
        }
        throw new InvalidDataException("Request line is too long");
    }

    private static FileStream OpenInput(IDictionary<string, string> roots, string[] command, out long size)
    {
        string root;
        if (command.Length != 3 || !roots.TryGetValue(command[0], out root)
            || !Format[command[0]].IsMatch(command[1])
            || !long.TryParse(command[2], NumberStyles.None, CultureInfo.InvariantCulture, out size)
            || size <= 0 || size > 64L * 1024 * 1024)
            throw new InvalidDataException("Input is outside the allowed dataset");

        string path = root;
        foreach (string segment in command[1].Split('/')) {
            path = Path.Combine(path, segment);
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Reparse points are not served");
        }
        FileStream file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
                                         256 * 1024, FileOptions.SequentialScan);
        if (file.Length != size) {
            file.Dispose();
            throw new InvalidDataException("Dataset file length differs");
        }
        return file;
    }

    private static void Serve(TcpClient client, IDictionary<string, string> roots, string key)
    {
        long bytes = 0;
        int files = 0;
        using (client) {
            client.NoDelay = true;
            client.SendTimeout = 30000;
            using (NetworkStream stream = client.GetStream()) {
                if (!String.Equals(ReadLine(stream), "V32GA1 " + key, StringComparison.Ordinal)) {
                    stream.WriteByte((byte)'N');
                    return;
                }
                stream.WriteByte((byte)'Y');
                byte[] buffer = new byte[1024 * 1024];
                string line;
                while ((line = ReadLine(stream)) != null) {
                    FileStream input;
                    long size;
                    try { input = OpenInput(roots, line.Split(' '), out size); }
                    catch (InvalidDataException) { stream.WriteByte((byte)'N'); return; }
                    catch (IOException) { stream.WriteByte((byte)'N'); return; }
                    catch (UnauthorizedAccessException) { stream.WriteByte((byte)'N'); return; }
                    using (input) {
                        stream.WriteByte((byte)'Y');
                        long sent = 0;
                        while (sent < size) {
                            int n = input.Read(buffer, 0, (int)Math.Min(buffer.Length, size - sent));
                            if (n <= 0) throw new EndOfStreamException("Fixture changed during read");
                            stream.Write(buffer, 0, n);
                            sent += n;
                        }
                        bytes += sent;
                        files++;
                    }
                }
            }
        }
        Console.WriteLine("GA_STREAM_SESSION files={0} bytes={1}", files, bytes);
    }

    public static void Run(string bindIPv4, string boardIPv4, int port, string key, Hashtable paths)
    {
        IPAddress bind = IPAddress.Parse(bindIPv4), board = IPAddress.Parse(boardIPv4);
        if (bind.AddressFamily != AddressFamily.InterNetwork || board.AddressFamily != AddressFamily.InterNetwork
            || bind.Equals(IPAddress.Any) || board.Equals(IPAddress.Any))
            throw new ArgumentException("Specify the PC and VEK280 IPv4 addresses");
        var roots = new Dictionary<string, string>();
        foreach (DictionaryEntry entry in paths) {
            string layer = (string)entry.Key;
            if (!Format.ContainsKey(layer)) throw new ArgumentException("Unknown GA layer");
            string path = Path.GetFullPath((string)entry.Value);
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException("Use the dataset's actual directory");
            roots.Add(layer, path);
        }
        var listener = new TcpListener(bind, port);
        var slots = new SemaphoreSlim(4);
        listener.Start(4);
        Console.WriteLine("READY_GA_INPUT {0}:{1} board={2} layers={3}", bind, port, board, String.Join(",", roots.Keys));
        try {
            while (true) {
                TcpClient client = listener.AcceptTcpClient();
                if (!((IPEndPoint)client.Client.RemoteEndPoint).Address.Equals(board) || !slots.Wait(0)) {
                    client.Close();
                    continue;
                }
                ThreadPool.QueueUserWorkItem(delegate {
                    try { Serve(client, roots, key); }
                    catch (InvalidDataException e) { Console.WriteLine("GA_STREAM_CLOSED " + e.Message); }
                    catch (IOException e) { Console.WriteLine("GA_STREAM_CLOSED " + e.Message); }
                    catch (SocketException e) { Console.WriteLine("GA_STREAM_CLOSED " + e.Message); }
                    finally { slots.Release(); }
                });
            }
        } finally { listener.Stop(); }
    }
}
