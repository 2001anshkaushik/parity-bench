"""Minimal class-file disassembler (P1-B: reads the engine's Tika wrapper; no JDK on the laptop) (javap -c -p equivalent enough to read call sites and constants).
usage: minijavap.py <file.class> [method-name-filter]"""
import struct, sys

OPS = {0:'nop',1:'aconst_null',2:'iconst_m1',3:'iconst_0',4:'iconst_1',5:'iconst_2',6:'iconst_3',7:'iconst_4',8:'iconst_5',
9:'lconst_0',10:'lconst_1',11:'fconst_0',12:'fconst_1',13:'fconst_2',14:'dconst_0',15:'dconst_1',16:'bipush',17:'sipush',
18:'ldc',19:'ldc_w',20:'ldc2_w',21:'iload',22:'lload',23:'fload',24:'dload',25:'aload',26:'iload_0',27:'iload_1',28:'iload_2',
29:'iload_3',30:'lload_0',31:'lload_1',32:'lload_2',33:'lload_3',34:'fload_0',35:'fload_1',36:'fload_2',37:'fload_3',
38:'dload_0',39:'dload_1',40:'dload_2',41:'dload_3',42:'aload_0',43:'aload_1',44:'aload_2',45:'aload_3',46:'iaload',47:'laload',
48:'faload',49:'daload',50:'aaload',51:'baload',52:'caload',53:'saload',54:'istore',55:'lstore',56:'fstore',57:'dstore',58:'astore',
59:'istore_0',60:'istore_1',61:'istore_2',62:'istore_3',63:'lstore_0',64:'lstore_1',65:'lstore_2',66:'lstore_3',67:'fstore_0',
68:'fstore_1',69:'fstore_2',70:'fstore_3',71:'dstore_0',72:'dstore_1',73:'dstore_2',74:'dstore_3',75:'astore_0',76:'astore_1',
77:'astore_2',78:'astore_3',79:'iastore',80:'lastore',81:'fastore',82:'dastore',83:'aastore',84:'bastore',85:'castore',86:'sastore',
87:'pop',88:'pop2',89:'dup',90:'dup_x1',91:'dup_x2',92:'dup2',93:'dup2_x1',94:'dup2_x2',95:'swap',96:'iadd',97:'ladd',98:'fadd',
99:'dadd',100:'isub',101:'lsub',102:'fsub',103:'dsub',104:'imul',105:'lmul',106:'fmul',107:'dmul',108:'idiv',109:'ldiv',110:'fdiv',
111:'ddiv',112:'irem',113:'lrem',114:'frem',115:'drem',116:'ineg',117:'lneg',118:'fneg',119:'dneg',120:'ishl',121:'lshl',122:'ishr',
123:'lshr',124:'iushr',125:'lushr',126:'iand',127:'land',128:'ior',129:'lor',130:'ixor',131:'lxor',132:'iinc',133:'i2l',134:'i2f',
135:'i2d',136:'l2i',137:'l2f',138:'l2d',139:'f2i',140:'f2l',141:'f2d',142:'d2i',143:'d2l',144:'d2f',145:'i2b',146:'i2c',147:'i2s',
148:'lcmp',149:'fcmpl',150:'fcmpg',151:'dcmpl',152:'dcmpg',153:'ifeq',154:'ifne',155:'iflt',156:'ifge',157:'ifgt',158:'ifle',
159:'if_icmpeq',160:'if_icmpne',161:'if_icmplt',162:'if_icmpge',163:'if_icmpgt',164:'if_icmple',165:'if_acmpeq',166:'if_acmpne',
167:'goto',168:'jsr',169:'ret',170:'tableswitch',171:'lookupswitch',172:'ireturn',173:'lreturn',174:'freturn',175:'dreturn',
176:'areturn',177:'return',178:'getstatic',179:'putstatic',180:'getfield',181:'putfield',182:'invokevirtual',183:'invokespecial',
184:'invokestatic',185:'invokeinterface',186:'invokedynamic',187:'new',188:'newarray',189:'anewarray',190:'arraylength',
191:'athrow',192:'checkcast',193:'instanceof',194:'monitorenter',195:'monitorexit',196:'wide',197:'multianewarray',198:'ifnull',
199:'ifnonnull',200:'goto_w',201:'jsr_w'}
ARG = {16:1,17:2,18:1,19:2,20:2,21:1,22:1,23:1,24:1,25:1,54:1,55:1,56:1,57:1,58:1,132:2,169:1,178:2,179:2,180:2,181:2,182:2,
183:2,184:2,185:4,186:4,187:2,188:1,189:2,192:2,193:2,197:3,200:4,201:4}
for o in range(153, 169): ARG[o] = 2
ARG[198] = ARG[199] = 2
CPREF = {18, 19, 20, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 189, 192, 193, 197}


def parse(path):
    s, f, m = parse_bytes(open(path, 'rb').read())
    return s, f, [(a, b, c) for a, b, c, _o in m]


def parse_bytes(b):
    p = 10
    n = struct.unpack('>H', b[8:10])[0]; cp = [None] * n; i = 1
    while i < n:
        t = b[p]; p += 1
        if t == 1:
            l = struct.unpack('>H', b[p:p+2])[0]; cp[i] = ('utf8', b[p+2:p+2+l].decode('utf8', 'replace')); p += 2 + l
        elif t in (3, 4): cp[i] = ('int' if t == 3 else 'float', struct.unpack('>i' if t == 3 else '>f', b[p:p+4])[0]); p += 4
        elif t in (5, 6): cp[i] = ('long' if t == 5 else 'double', struct.unpack('>q' if t == 5 else '>d', b[p:p+8])[0]); p += 8; i += 1
        elif t in (7, 8, 16, 19, 20): cp[i] = ({7:'class',8:'string',16:'mtype',19:'module',20:'package'}[t], struct.unpack('>H', b[p:p+2])[0]); p += 2
        elif t in (9, 10, 11, 12, 17, 18): cp[i] = ({9:'field',10:'method',11:'imethod',12:'nat',17:'dyn',18:'indy'}[t],) + struct.unpack('>HH', b[p:p+4]); p += 4
        elif t == 15: cp[i] = ('mhandle', b[p], struct.unpack('>H', b[p+1:p+3])[0]); p += 3
        else: raise ValueError(f'tag {t} at {p}')
        i += 1

    def s(k):
        e = cp[k]
        if e is None: return '?'
        if e[0] == 'utf8': return e[1]
        if e[0] in ('class', 'string', 'mtype'): return s(e[1])
        if e[0] in ('field', 'method', 'imethod'): return f'{s(e[1])}.{s(e[2])}'
        if e[0] == 'nat': return f'{s(e[1])}:{s(e[2])}'
        if e[0] in ('dyn', 'indy'): return f'indy#{e[1]}:{s(e[2])}'
        return repr(e[1:])
    p += 6
    ic = struct.unpack('>H', b[p:p+2])[0]; p += 2 + 2 * ic

    def attrs(p):
        c = struct.unpack('>H', b[p:p+2])[0]; p += 2; out = []
        for _ in range(c):
            nm = s(struct.unpack('>H', b[p:p+2])[0]); l = struct.unpack('>I', b[p+2:p+6])[0]
            out.append((nm, b[p+6:p+6+l], p + 6)); p += 6 + l
        return p, out
    fc = struct.unpack('>H', b[p:p+2])[0]; p += 2; fields = []
    for _ in range(fc):
        fl, nm, ds = struct.unpack('>HHH', b[p:p+6]); p, _a = attrs(p + 6); fields.append((s(nm), s(ds)))
    mc = struct.unpack('>H', b[p:p+2])[0]; p += 2; methods = []
    for _ in range(mc):
        fl, nm, ds = struct.unpack('>HHH', b[p:p+6]); p, at = attrs(p + 6)
        code = next(((v, o) for k, v, o in at if k == 'Code'), (None, None))
        methods.append((s(nm), s(ds), code[0], code[1]))
    return s, fields, methods


def dis(code, s):
    cl = struct.unpack('>I', code[4:8])[0]; c = code[8:8+cl]; i = 0; out = []
    while i < len(c):
        op = c[i]; name = OPS.get(op, f'op{op}'); start = i
        if op == 170:
            j = (i + 4) & ~3; lo, hi = struct.unpack('>ii', c[j+4:j+12]); i = j + 12 + 4 * (hi - lo + 1); out.append((start, name, '')); continue
        if op == 171:
            j = (i + 4) & ~3; np_ = struct.unpack('>i', c[j+4:j+8])[0]; i = j + 8 + 8 * np_; out.append((start, name, '')); continue
        if op == 196:
            op2 = c[i+1]; i += 6 if op2 == 132 else 4; out.append((start, 'wide', OPS.get(op2))); continue
        n = ARG.get(op, 0); arg = ''
        if n:
            raw = c[i+1:i+1+n]
            if op in CPREF:
                k = raw[0] if op == 18 else struct.unpack('>H', raw[:2])[0]; arg = s(k)
            elif op in (16,): arg = str(struct.unpack('>b', raw)[0])
            elif op in (17,): arg = str(struct.unpack('>h', raw)[0])
            elif 153 <= op <= 168 or op in (198, 199): arg = f'-> {start + struct.unpack(">h", raw)[0]}'
            else: arg = raw.hex()
        out.append((start, name, arg)); i += 1 + n
    return out


if __name__ == '__main__':
    s, fields, methods = parse(sys.argv[1]); flt = sys.argv[2] if len(sys.argv) > 2 else None
    print('FIELDS:', ', '.join(f'{a}:{b}' for a, b in fields))
    for nm, ds, code in methods:
        if flt and flt not in nm: continue
        print(f'\n== {nm}{ds}')
        if code:
            for off, op, arg in dis(code, s): print(f'  {off:5d} {op} {arg}')
