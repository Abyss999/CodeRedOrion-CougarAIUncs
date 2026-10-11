"""Light artboard -> dark artboard, using DESIGN_SYSTEM.md dark tokens (and Theme.swift food-group darks).
Property-aware: background colours map to dark grounds, foreground (color/stroke/fill/border/shadow) to dark inks.
Inside an element whose background is lime (lime stays lime in dark) or the camera surface (#1B2A1F, a
viewfinder that is dark in both modes), foreground colours keep their light values.
On forestChip (#2F6B3C) the text is onForestChip: light text in both modes.

Every colour the converter handles is marked while it runs. Afterwards, any light-only token that was
never handled (a colour passed as a positional argument, built by concatenation, a short hex, a named
colour, a light rgba) fails the run with a list, so a light row can't slip into a dark artboard.

Usage: python3 mkdark.py <light-screens-dir> <out-dir>   (*.dark.dc.html inputs are skipped)"""
import re, sys, collections
BG = {"F4F8E8":"0F1A12","FFFFFF":"18261B","EEF5D6":"24361F","E3EDCB":"223024","E6EDD6":"2A3A2D","1F4D2B":"B9D871",
 "3B7046":"8FB45A","2F6B3C":"2C4A26","D9EC8F":"D9EC8F","FBE3CF":"4A2614","FFF6C7":"3A3720","E4F2C4":"2A3A1F","FFF1B8":"3A3112",
 "4C5A4F":"050806","C3D1B3":"34483A","D3E0BF":"34483A","277338":"24783D","E8A04C":"C6802F","13261A":"E8F0DA","1B2A1F":"0F1A12",
 "FBE4DE":"3D1F1A","E2F1D8":"1C3320","F8E1EC":"3A1C2B","E2E9F7":"1C2540","F5EBCD":"33290F","ECE5F7":"2A2140","DAF0EE":"14302F","DCEFF8":"122C3A","EAEFE6":"243026","8E978F":"0A110C","EAF0DA":"223024","8FB43A":"8FB45A","6B5000":"FFD970"}
FG = {"13261A":"E8F0DA","2B3D30":"C9D6BC","45584A":"9DB09F","4F6152":"8FA391","5C6E5F":"8FA391","1F4D2B":"B9D871","3B7046":"8FB45A",
 "2F6B3C":"2C4A26","F4F8E8":"13261A","D9EC8F":"13261A","C9D8BE":"2F4A2A","8A3B0E":"FFB98A","6B5000":"FFD970","D3E0BF":"34483A",
 "E6EDD6":"2A3A2D","C3D1B3":"34483A","EEF5D6":"24361F","E3EDCB":"223024","277338":"24783D","E8A04C":"C6802F","747775":"8E918F","1F1F1F":"E3E3E3",
 "FBE3CF":"4A2614","1B2A1F":"E8F0DA","FFF1B8":"3A3112",
 "B0412E":"FF9E8A","2F7A3A":"8FD69A","A8366E":"F59AC6","3A5BA0":"9DB7F0","8A6414":"E8C46A","6A4FA3":"C1AAF0","1F7A78":"7FD8D3","1E7BA8":"86CBEE"}
KEEP = {"FFFFFF","4285F4","34A853","FBBC05","EA4335"}  # fg kept as is
RGBA = [(r"rgba\(255,\s*255,\s*255,\s*0?\.8\)","rgba(24,38,27,0.82)"),(r"rgba\(255,\s*255,\s*255,\s*0?\.7\)","rgba(255,255,255,0.08)"),
 (r"rgba\(31,\s*77,\s*43,\s*0?\.12\)","rgba(185,216,113,0.16)"),(r"rgba\(19,\s*38,\s*26,\s*0?\.14\)","rgba(0,0,0,0.5)"),(r"rgba\(31,\s*77,\s*43,\s*0?\.12\)","rgba(0,0,0,0.4)"),
 (r"rgba\(138,\s*59,\s*14,","rgba(255,185,138,"),
 # Undo toast (as shipped, #64): capsule, progress track and fill, shadow
 (r"rgba\(255,\s*255,\s*255,\s*0?\.18\)","rgba(0,0,0,0.16)"),(r"rgba\(255,\s*255,\s*255,\s*0?\.1\)","rgba(0,0,0,0.12)"),
 (r"rgba\(244,\s*248,\s*232,\s*0?\.8\)","rgba(19,38,26,0.85)"),(r"rgba\(19,\s*38,\s*26,\s*0?\.28\)","rgba(0,0,0,0.5)")]
HEX = re.compile(r"#([0-9A-Fa-f]{6})\b")
MARK = "\x00"   # put after '#' on every handled colour; stripped before writing
KEEP_BG = ("#D9EC8F", "#1B2A1F")   # lime card, camera surface: foreground keeps its light value
CHIP_BG = "#2F6B3C"                # forestChip: text is onForestChip (light in both modes)
miss = collections.Counter()
def m(table, h, lime):
    H = h.upper()
    if lime and table is FG: return MARK + h  # dark-on-lime stays
    if H in table: return MARK + table[H]
    if table is FG and H in KEEP: return MARK + h
    miss[H]+=1; return MARK + h
def keeps(bg): return any(k in bg.upper() for k in KEEP_BG)
def css(s, lime=False):
    """Rewrite a CSS declaration string (style attr, JS style string, helmet rule)."""
    bgm = re.search(r"background(?:-color)?\s*:\s*([^;]+)", s, re.I)
    if bgm and keeps(bgm.group(1)): lime = True
    chip = bool(bgm) and CHIP_BG in bgm.group(1).upper()
    def decl(mo):
        prop, val = mo.group(1), mo.group(2)
        table = BG if prop.strip().lower() in ("background","background-color") else FG
        return prop + ":" + HEX.sub(lambda h: "#"+m(table, h.group(1), lime and table is FG), val)
    s = re.sub(r"([a-zA-Z-]+\s*):([^;{}]*)", decl, s)
    if chip:  # onForestChip: light text on the chip in dark too
        s = re.sub(r"((?:^|;)\s*color\s*:\s*#)" + MARK + r"13261A", r"\g<1>" + MARK + "E8F0DA", s)
    for a,b in RGBA: s = re.sub(a,b,s)
    return s
VOID = {"area","base","br","col","embed","hr","img","input","link","meta","source","track","wbr"}
def html(src):
    out=[]; pos=0; stack=[False]
    for mo in re.finditer(r"<(/?)([a-zA-Z][\w-]*)((?:\"[^\"]*\"|'[^']*'|[^'\">])*)>", src):
        out.append(src[pos:mo.start()]); pos=mo.end()
        close, tag, attrs = mo.groups()
        if close:
            if len(stack)>1: stack.pop()
            out.append(mo.group(0)); continue
        parent = stack[-1]
        sm = re.search(r'style="([^"]*)"', attrs)
        own_lime = parent
        if sm:
            st = sm.group(1)
            bgm = re.search(r"background(?:-color)?\s*:\s*([^;]+)", st, re.I)
            if bgm: own_lime = keeps(bgm.group(1))
            attrs = attrs.replace(sm.group(0), 'style="'+css(st, own_lime)+'"')
        attrs = re.sub(r'\b(stroke|fill)="#([0-9A-Fa-f]{6})"', lambda a: a.group(1)+'="#'+m(FG,a.group(2),own_lime)+'"', attrs)
        out.append("<"+tag+attrs+">")
        if tag.lower() not in VOID and not attrs.rstrip().endswith("/"): stack.append(own_lime)
    out.append(src[pos:]); return "".join(out)
BGKEY = re.compile(r"\w*(?:[bB]g|[bB]ackground)\w*$")
def script(js):
    # Background-valued keys whose value is an expression with bare colour literals, e.g.
    # `rowBg: on ? '#EEF5D6' : '#FFFFFF'`. Runs first, on the raw light values, so nothing is mapped twice.
    js = re.sub(r"\b(\w*(?:[bB]g|[bB]ackground)\w*)\s*:([^,\n}]*)",
                lambda a: a.group(1)+":"+re.sub(r"'#([0-9A-Fa-f]{6})'", lambda h: "'#"+m(BG,h.group(1),False)+"'", a.group(2)), js)
    # Foreground-valued keys (stroke, fill, color and any *Stroke / *Fill / *Color such as `checkStroke`),
    # including ternaries: `checkStroke: checked ? '#1F4D2B' : 'transparent'`.
    def fgkey(a):
        if BGKEY.match(a.group(1)): return a.group(0)
        return a.group(1)+":"+re.sub(r"'#([0-9A-Fa-f]{6})'", lambda h: "'#"+m(FG,h.group(1),False)+"'", a.group(2))
    js = re.sub(r"\b(\w*(?:[sS]troke|[fF]ill|[cC]olor))\s*:([^,\n}]*)", fgkey, js)
    js = re.sub(r"tile\('#([0-9A-Fa-f]{6})'\)", lambda a: "tile('#"+m(BG,a.group(1),False)+"')", js)
    js = re.sub(r"'([^'\n]*:[^'\n]*#[0-9A-Fa-f]{6}[^'\n]*)'", lambda a: "'"+css(a.group(1))+"'", js)
    return js
LIGHT_ONLY = (set(BG) | set(FG)) - set(BG.values()) - set(FG.values()) - {"D9EC8F", "FFFFFF"}
def leftovers(s):
    """Colours the converter never handled, or that can't be mapped by token."""
    bad = []
    for i, line in enumerate(s.splitlines(), 1):
        for h in HEX.findall(line):
            # Every colour the converter handles carries MARK, so any plain hex here was never seen:
            # a positional argument, a concatenation or an unknown key. Fail on all of them, dark-looking ones too.
            bad.append((i, "#"+h, "colour never handled (positional arg, concatenation or unknown key?)"))
        for h in re.findall(r"#[0-9A-Fa-f]{8}\b", line): bad.append((i, h, "8-digit hex is not supported; use rgba()"))
        for h in re.findall(r"#[0-9A-Fa-f]{3}\b", line): bad.append((i, h, "short hex"))
        for c in re.findall(r"(?:color|background|fill|stroke|border)[\w-]*\s*[:=]\s*['\"]?(white|ivory|snow|whitesmoke|beige)\b", line, re.I):
            bad.append((i, c, "named light colour"))
        for r, g, b, a in re.findall(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\)", line):
            if min(int(r), int(g), int(b)) >= 200 and float(a or 1) > 0.3: bad.append((i, f"rgba({r},{g},{b},{a or 1})", "light rgba"))
    return bad
def convert(src):
    hs, he = src.index("<helmet>"), src.index("</helmet>")
    helmet = src[hs:he]
    helmet = re.sub(r"<style>(.*?)</style>", lambda a: "<style>"+css(a.group(1))+"\nbody{background:#"+MARK+"0F1A12}</style>", helmet, flags=re.S)
    ss = src.index('<script type="text/x-dc"')
    body = html(src[he:ss])
    return src[:hs] + helmet + body + script(src[ss:])
if __name__ == "__main__":
    src_dir, out_dir = sys.argv[1], sys.argv[2]
    import os, glob
    failures = []
    for p in sorted(glob.glob(os.path.join(src_dir, "*.dc.html"))):
        if ".dark." in os.path.basename(p): continue
        name = os.path.basename(p).replace(".dc.html", ".dark.dc.html")
        s = convert(open(p).read())
        failures += [(name,) + b for b in leftovers(s)]
        s = s.replace("#" + MARK, "#").replace("<title>", "<title>Dark: ", 1)
        open(os.path.join(out_dir, name), "w").write(s)
    light_miss = {h: n for h, n in miss.items() if h in LIGHT_ONLY}
    print("unmapped:", dict(miss))
    if failures or light_miss:
        for f in failures: print("FAIL %s:%d %s (%s)" % f, file=sys.stderr)
        for h, n in light_miss.items(): print("FAIL light-only #%s has no dark value (%d uses)" % (h, n), file=sys.stderr)
        sys.exit(1)
