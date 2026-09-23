import java.io.*;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import org.apache.tika.config.TikaConfig;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.parser.Parser;
import org.apache.tika.sax.BodyContentHandler;

/** P0 (H5/H6): the ENGINE'S OWN Tika, outside the engine, timed per document.
 *
 *  Same jars and bundled JRE as the engine (run inside rr:patched with the entrypoint replaced),
 *  same extraction call as TikaExtract (AutoDetectParser + BodyContentHandler(-1)), and a
 *  tika-config.xml given per run so H5 can switch ONE PDFParser feature at a time.
 *
 *  Protocol: prints {"ready":true}, then reads one absolute path per line on stdin and answers
 *  one JSON line per path: wall_s and cpu_s of the parse call alone (System.nanoTime and this
 *  thread's CPU time around parse(), so JVM start-up and file writing are excluded), the text's
 *  UTF-16 length, and the exception if one was thrown. The extracted text is written as UTF-8 to
 *  <out_dir>/<name>.txt so every parser's text can be compared by one reader. A document that
 *  hangs is the orchestrator's to time out: it kills this JVM and starts another. */
public class TikaBatch {
  static String esc(String s) {
    StringBuilder b = new StringBuilder();
    for (char c : s.toCharArray()) {
      if (c == '"' || c == '\\') b.append('\\').append(c);
      else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
      else b.append(c);
    }
    return b.toString();
  }

  public static void main(String[] a) throws Exception {
    TikaConfig cfg = new TikaConfig(new File(a[0]));
    Path outDir = (a.length > 1 && !a[1].equals("-")) ? Paths.get(a[1]) : null;
    Parser p = new AutoDetectParser(cfg);
    ThreadMXBean tb = ManagementFactory.getThreadMXBean();
    BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    // The protocol owns stdout. Library code that prints to System.out (seen on 040_040669.pdf in the
    // H6 smoke) would otherwise interleave with the JSON lines, so System.out now goes to stderr.
    PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
    System.setOut(System.err);
    out.println("{\"ready\":true,\"config\":\"" + esc(a[0]) + "\"}");
    String line;
    while ((line = in.readLine()) != null) {
      line = line.trim();
      if (line.isEmpty()) continue;
      Path f = Paths.get(line);
      String name = f.getFileName().toString();
      String err = null;
      String text = "";
      long c0 = tb.getCurrentThreadCpuTime();
      long t0 = System.nanoTime();
      try (InputStream is = Files.newInputStream(f)) {
        BodyContentHandler h = new BodyContentHandler(-1);
        p.parse(is, h, new Metadata(), new ParseContext());
        text = h.toString();
      } catch (Throwable e) {
        err = e.getClass().getName() + ": " + String.valueOf(e.getMessage());
      }
      long t1 = System.nanoTime();
      long c1 = tb.getCurrentThreadCpuTime();
      if (outDir != null && err == null) {
        Files.write(outDir.resolve(name + ".txt"), text.getBytes(StandardCharsets.UTF_8));
      }
      out.println("{\"doc\":\"" + esc(name) + "\",\"wall_s\":" + ((t1 - t0) / 1e9)
          + ",\"cpu_s\":" + ((c1 - c0) / 1e9) + ",\"jchars\":" + text.length()
          + (err == null ? "" : ",\"error\":\"" + esc(err) + "\"") + "}");
    }
  }
}
