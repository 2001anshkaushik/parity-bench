import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import org.apache.tika.config.TikaConfig;
import org.apache.tika.metadata.Metadata;
import org.apache.tika.parser.AutoDetectParser;
import org.apache.tika.parser.ParseContext;
import org.apache.tika.parser.Parser;
import org.apache.tika.sax.BodyContentHandler;

/** Standalone Tika extraction using the ENGINE'S OWN jars and tika-config.xml.
 *  Independent of the engine process, but the same parser — so it can falsify the engine
 *  without reintroducing pypdf-as-truth. */
public class TikaExtract {
  public static void main(String[] args) throws Exception {
    TikaConfig cfg = args.length > 1 ? new TikaConfig(new File(args[1])) : TikaConfig.getDefaultConfig();
    Parser p = new AutoDetectParser(cfg);
    BodyContentHandler h = new BodyContentHandler(-1);   // -1 = no write limit
    Metadata md = new Metadata();
    try (InputStream in = Files.newInputStream(Paths.get(args[0]))) {
      p.parse(in, h, md, new ParseContext());
    }
    PrintStream out = new PrintStream(System.out, true, StandardCharsets.UTF_8);
    out.print(h.toString());
  }
}
