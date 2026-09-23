#!/usr/bin/env python3
"""P1-B PATCH: turn off PDF inline-image extraction in the engine's Tika wrapper — ONE byte.

    p1_patch_tikaapi.py <tika.jar in> <tika.jar out>

com/rocketride/tika_api/TikaApi.getPdfConfig() hard-codes
     8 aload_0 ;  9 iconst_1 ; 10 invokevirtual PDFParserConfig.setExtractInlineImages(Z)V
and extractInformation() sets that PDFParserConfig into the ParseContext (offsets 564-571), where it
overrides tika-config.xml's PDFParser params — no setting reaches it. This flips code byte 9 from
iconst_1 (0x04) to iconst_0 (0x03). Every other byte of the class and every other jar entry is
copied unchanged; the patched class is disassembled again and the change asserted."""
import io
import struct
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minijavap  # noqa: E402

CLS = "com/rocketride/tika_api/TikaApi.class"


def code_offset(raw: bytes, method: str) -> int:
    """File offset of the first bytecode byte of `method`'s Code attribute."""
    s, _f, methods = minijavap.parse_bytes(raw)
    for nm, _ds, code, code_file_off in methods:
        if nm == method and code is not None:
            return code_file_off + 8          # Code attr body: max_stack(2) max_locals(2) code_length(4)
    raise SystemExit(f"method {method} not found")


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    zin = zipfile.ZipFile(src)
    if any(n.upper().endswith((".SF", ".RSA", ".DSA", ".EC")) for n in zin.namelist() if n.upper().startswith("META-INF/")):
        raise SystemExit("REFUSED: the jar is signed; patching would break its signature")
    raw = bytearray(zin.read(CLS))
    off = code_offset(bytes(raw), "getPdfConfig")
    s, _f, methods = minijavap.parse_bytes(bytes(raw))
    ins = {o: (op, arg) for m in methods if m[0] == "getPdfConfig" for o, op, arg in minijavap.dis(m[2], s)}
    assert ins[8][0] == "aload_0" and ins[9][0] == "iconst_1", ins
    assert ins[10] == ("invokevirtual", "org/apache/tika/parser/pdf/PDFParserConfig.setExtractInlineImages:(Z)V"), ins[10]
    assert raw[off + 9] == 0x04 and raw[off + 10] == 0xB6
    raw[off + 9] = 0x03
    s2, _f2, methods2 = minijavap.parse_bytes(bytes(raw))
    ins2 = {o: (op, arg) for m in methods2 if m[0] == "getPdfConfig" for o, op, arg in minijavap.dis(m[2], s2)}
    assert ins2[9][0] == "iconst_0" and ins2[10] == ins[10] and ins2[14][0] == "iconst_1", ins2
    diff = [i for i, (a, b) in enumerate(zip(zin.read(CLS), raw)) if a != b]
    assert diff == [off + 9], diff
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            data = bytes(raw) if info.filename == CLS else zin.read(info.filename)
            zout.writestr(info, data)
    dst.write_bytes(buf.getvalue())
    print(f"patched {CLS}: file offset {off + 9} (getPdfConfig code byte 9) 0x04 iconst_1 -> 0x03 iconst_0; "
          f"setExtractInlineImages(false); setExtractUniqueInlineImagesOnly and every other byte unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
