import re, io, os, uuid, math

SY = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/"
LOCAL_LIB = "kali.kicad_sym"
PROJ = "kali-tank-sensor-v3"
ROOT_UUID = "0f1e2d3c-4b5a-4697-8899-aabbccddeeff"

def U(): return str(uuid.uuid4())

def find_block(text, name):
    i = text.find(f'(symbol "{name}"')
    if i < 0: return None
    d = 0; j = i
    while j < len(text):
        if text[j] == '(': d += 1
        elif text[j] == ')':
            d -= 1
            if d == 0: return text[i:j+1]
        j += 1
    return None

_cache = {}
def load_lib(libname):
    if libname in _cache: return _cache[libname]
    path = LOCAL_LIB if libname == "kali" else SY + libname + ".kicad_sym"
    _cache[libname] = io.open(path, encoding="utf-8").read()
    return _cache[libname]

def sym_block(lib_id):
    lib, name = lib_id.split(":")
    txt = load_lib(lib)
    b = find_block(txt, name)
    if b is None: raise SystemExit(f"symbol not found: {lib_id}")
    return b, txt, name

def resolve_pins(lib_id):
    """Return [(number, x, y, angle)] in library coords, following 'extends'."""
    b, txt, name = sym_block(lib_id)
    ext = re.findall(r'\(extends "([^"]+)"', b)
    src = b
    if ext:
        src = find_block(txt, ext[0])
    out = []
    for m in re.finditer(r'\(pin\s+\S+\s+\S+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)', src):
        seg = src[m.start():m.start()+400]
        nu = re.search(r'\(number "([^"]*)"', seg)
        if nu:
            out.append((nu.group(1), float(m.group(1)), float(m.group(2)), int(m.group(3))))
    return out

def lib_symbol_defs(lib_ids):
    """Emit (lib_symbols ...) entries. Derived symbols are FLATTENED against their
    parent so no (extends ...) reference has to be resolved by the reader."""
    chunks, done = [], set()
    for lid in lib_ids:
        if lid in done: continue
        done.add(lid)
        lib, name = lid.split(":")
        b, txt, _ = sym_block(lid)
        ext = re.findall(r'\(extends "([^"]+)"', b)
        if ext:
            parent = ext[0]
            pb = find_block(txt, parent)
            # rename parent's sub-symbols to the child's bare name, drop the prefix there
            pb = re.sub(r'\(symbol "' + re.escape(parent) + r'_(\d+_\d+)"',
                        lambda m: f'(symbol "{name}_{m.group(1)}"', pb)
            pb = pb.replace(f'(symbol "{parent}"', f'(symbol "{lid}"', 1)
            pb = re.sub(r'\(property "Value" "' + re.escape(parent) + r'"',
                        f'(property "Value" "{name}"', pb, count=1)
            # carry over the child's own property overrides so the schematic cache
            # matches what KiCad itself would write (avoids lib_symbol_mismatch)
            for pname in ["Reference","Value","Footprint","Datasheet","Description",
                          "ki_keywords","ki_fp_filters"]:
                cm = re.search(r'\(property "' + pname + r'" "([^"]*)"', b)
                if cm:
                    pb2, n = re.subn(r'(\(property "' + pname + r'" ")[^"]*(")',
                                     lambda m: m.group(1)+cm.group(1)+m.group(2), pb, count=1)
                    if n:
                        pb = pb2
                    else:
                        # parent lacks this property entirely -> insert the child's copy
                        anchor = pb.find('(property "Datasheet"')
                        if anchor > 0:
                            d2 = 0; k = anchor
                            while k < len(pb):
                                if pb[k] == '(': d2 += 1
                                elif pb[k] == ')':
                                    d2 -= 1
                                    if d2 == 0: break
                                k += 1
                            ins = ('\n\t\t(property "' + pname + '" "' + cm.group(1) + '"'
                                   '\n\t\t\t(at 0 0 0)'
                                   '\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)'
                                   '\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)')
                            pb = pb[:k+1] + ins + pb[k+1:]
            body = pb
        else:
            body = b.replace(f'(symbol "{name}"', f'(symbol "{lid}"', 1)
        chunks.append("\t\t" + body.replace("\n", "\n\t\t"))
    return "\n".join(chunks)

def G(v):
    return round(round(v/2.54)*2.54, 2)

# ---------------- design ----------------
# ref: (lib_id, value, footprint, x, y)
COMPS = {
 "J1": ("kali:WirePad",            "12V IN +",   "kali:WirePad_StrainRelief",      30,  40),
 "F1": ("Device:Polyfuse",         "PTC 200mA",  "Resistor_SMD:R_1206_3216Metric", 55,  40),
 "D2": ("Device:D_TVS",            "SMBJ16A",    "Diode_SMD:D_SMB",                75,  55),
 "D1": ("Device:D_Schottky",       "SS34",       "Diode_SMD:D_SMA",                95,  40),
 "C4": ("Device:C",                "100nF/50V",  "Capacitor_SMD:C_0805_2012Metric",115, 55),
 "U3": ("kali:DCDC_3V3_Module",    "3V3 5-30V",  "kali:DCDC_Module_18x12_4pad",    150, 45),
 "J2": ("kali:WirePad",            "12V IN -",   "kali:WirePad_StrainRelief",      30,  70),

 "C2": ("Device:C",                "22uF",       "Capacitor_SMD:C_1206_3216Metric",195, 45),
 "C3": ("Device:C",                "22uF",       "Capacitor_SMD:C_1206_3216Metric",215, 45),
 "SB1":("kali:SolderBridge",       "3V3 FEED",   "kali:SolderBridge_2pad",         245, 40),

 "U1": ("kali:XIAO_ESP32C3",       "XIAO ESP32-C3","kali:XIAO-ESP32C3_TopSolder",   90, 150),
 "U2": ("Sensor_Energy:INA238",    "INA238AIDGSR","Package_SO:MSOP-10_3x3mm_P0.5mm",210,150),
 "C1": ("Device:C",                "100nF",      "Capacitor_SMD:C_0805_2012Metric",165, 200),
 "R5": ("Device:R",                "4k7",        "Resistor_SMD:R_0805_2012Metric", 150, 105),
 "R6": ("Device:R",                "4k7",        "Resistor_SMD:R_0805_2012Metric", 170, 105),

 "R1": ("Device:R",                "1R 0.1%",    "Resistor_SMD:R_0805_2012Metric", 285, 105),
 "R2": ("Device:R",                "100R",       "Resistor_SMD:R_0805_2012Metric", 285, 145),
 "J3": ("kali:WirePad",            "SENDER A",   "kali:WirePad_StrainRelief",      330, 145),
 "J4": ("kali:WirePad",            "SENDER B",   "kali:WirePad_StrainRelief",      330, 185),
 "Q1": ("Transistor_FET:AO3400A",  "AO3400A",    "Package_TO_SOT_SMD:SOT-23",      285, 200),
 "R3": ("Device:R",                "100R",       "Resistor_SMD:R_0805_2012Metric", 240, 215),
 "R4": ("Device:R",                "100k",       "Resistor_SMD:R_0805_2012Metric", 265, 240),
}

NETS = {
 ("J1","1"):"V12_IN", ("F1","1"):"V12_IN", ("F1","2"):"V12_F",
 ("D2","1"):"V12_F",  ("D2","2"):"GND",
 ("D1","2"):"V12_F",  ("D1","1"):"V12_P",
 ("C4","1"):"V12_P",  ("C4","2"):"GND",
 ("U3","1"):"V12_P",  ("U3","2"):"GND", ("U3","3"):"+3V3", ("U3","4"):"GND",
 ("J2","1"):"GND",
 ("C2","1"):"+3V3", ("C2","2"):"GND",
 ("C3","1"):"+3V3", ("C3","2"):"GND",
 ("SB1","1"):"+3V3", ("SB1","2"):"+3V3_MCU",
 ("U1","2"):"MEAS_EN", ("U1","5"):"SDA", ("U1","6"):"SCL",
 ("U1","11"):"VS_INA", ("U1","12"):"+3V3_MCU", ("U1","13"):"GND",
 ("U2","1"):"GND", ("U2","2"):"GND", ("U2","4"):"SDA", ("U2","5"):"SCL",
 ("U2","6"):"VS_INA", ("U2","7"):"GND", ("U2","8"):"NODE_A",
 ("U2","9"):"SHUNT_LO", ("U2","10"):"+3V3",
 ("C1","1"):"VS_INA", ("C1","2"):"GND",
 ("R5","1"):"VS_INA", ("R5","2"):"SDA",
 ("R6","1"):"VS_INA", ("R6","2"):"SCL",
 ("R1","1"):"+3V3", ("R1","2"):"SHUNT_LO",
 ("R2","1"):"SHUNT_LO", ("R2","2"):"NODE_A",
 ("J3","1"):"NODE_A", ("J4","1"):"NODE_B",
 ("Q1","1"):"GATE", ("Q1","2"):"GND", ("Q1","3"):"NODE_B",
 ("R3","1"):"MEAS_EN", ("R3","2"):"GATE",
 ("R4","1"):"GATE", ("R4","2"):"GND",
}
NC = [("U1","1"),("U1","3"),("U1","4"),("U1","7"),("U1","8"),("U1","9"),("U1","10"),
      ("U1","14"),("U2","3")]
PWR_FLAGS = ["V12_IN","V12_P","VS_INA","+3V3_MCU"]

out = []
out.append('(kicad_sch')
out.append('\t(version 20250114)')
out.append('\t(generator "eeschema")')
out.append('\t(generator_version "9.0")')
out.append(f'\t(uuid "{ROOT_UUID}")')
out.append('\t(paper "A3")')
out.append('\t(title_block')
out.append('\t\t(title "Kali Fresh Water Tank Sensor - rev 3")')
out.append('\t\t(date "2026-09-08")')
out.append('\t\t(rev "3.0")')
out.append('\t\t(company "boat-scripts / Kali")')
out.append('\t)')

used = sorted(set(v[0] for v in COMPS.values()) | {"power:PWR_FLAG"})
out.append('\t(lib_symbols')
out.append(lib_symbol_defs(used))
out.append('\t)')

wires, labels = [], []
def add_stub(px, py, ang, net):
    dx = -math.cos(math.radians(ang)) * 2.54
    dy =  math.sin(math.radians(ang)) * 2.54
    ex, ey = round(px+dx,2), round(py+dy,2)
    wires.append(f'\t(wire (pts (xy {px} {py}) (xy {ex} {ey})) (stroke (width 0) (type default)) (uuid "{U()}"))')
    just = "left" if dx >= 0 else "right"
    lang = 0 if abs(dx) >= abs(dy) else 90
    labels.append(
        f'\t(global_label "{net}" (shape bidirectional) (at {ex} {ey} {lang}) (fields_autoplaced yes)\n'
        f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
        f'\t\t(uuid "{U()}")\n'
        f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {ex} {ey} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t)')

for ref,(lid,val,fpname,X,Y) in COMPS.items():
    X, Y = G(X), G(Y)
    pins = resolve_pins(lid)
    out.append(f'\t(symbol (lib_id "{lid}") (at {X} {Y} 0) (unit 1)')
    out.append('\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)')
    out.append(f'\t\t(uuid "{U()}")')
    out.append(f'\t\t(property "Reference" "{ref}" (at {X+12} {Y-8} 0) (effects (font (size 1.27 1.27)) (justify left)))')
    out.append(f'\t\t(property "Value" "{val}" (at {X+12} {Y-5} 0) (effects (font (size 1.27 1.27)) (justify left)))')
    out.append(f'\t\t(property "Footprint" "{fpname}" (at {X} {Y} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
    out.append(f'\t\t(property "Datasheet" "~" (at {X} {Y} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
    for (num,px,py,ang) in pins:
        out.append(f'\t\t(pin "{num}" (uuid "{U()}"))')
    out.append(f'\t\t(instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))')
    out.append('\t)')
    for (num,px,py,ang) in pins:
        ax, ay = round(X+px,2), round(Y-py,2)
        key=(ref,num)
        if key in NETS: add_stub(ax, ay, ang, NETS[key])
        elif key in NC:
            out.append(f'\t(no_connect (at {ax} {ay}) (uuid "{U()}"))')

# PWR_FLAGs
pf_pins = resolve_pins("power:PWR_FLAG")
px0,py0,pa0 = pf_pins[0][1], pf_pins[0][2], pf_pins[0][3]
for i,net in enumerate(PWR_FLAGS):
    X, Y = G(40 + i*33), G(260)
    out.append(f'\t(symbol (lib_id "power:PWR_FLAG") (at {X} {Y} 0) (unit 1)')
    out.append('\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)')
    out.append(f'\t\t(uuid "{U()}")')
    out.append(f'\t\t(property "Reference" "#FLG{i+1}" (at {X} {Y-6} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
    out.append(f'\t\t(property "Value" "PWR_FLAG" (at {X} {Y-3} 0) (effects (font (size 1.27 1.27))))')
    out.append(f'\t\t(property "Footprint" "" (at {X} {Y} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
    out.append(f'\t\t(property "Datasheet" "~" (at {X} {Y} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
    out.append(f'\t\t(pin "1" (uuid "{U()}"))')
    out.append(f'\t\t(instances (project "{PROJ}" (path "/{ROOT_UUID}" (reference "#FLG{i+1}") (unit 1))))')
    out.append('\t)')
    add_stub(round(X+px0,2), round(Y-py0,2), pa0, net)

out += wires + labels
for txt,x,y in [("POWER INPUT  12V -> 3V3",30,25),("MEASUREMENT CHAIN  3V3 > R1 shunt > R2 > sender > Q1 > GND",240,90),
                ("MCU / I2C",90,105),("SB1: OPEN BEFORE CONNECTING USB",245,30)]:
    out.append(f'\t(text "{txt}" (exclude_from_sim no) (at {x} {y} 0)\n\t\t(effects (font (size 2 2) (thickness 0.3) (bold yes)) (justify left))\n\t\t(uuid "{U()}")\n\t)')

out.append('\t(sheet_instances (path "/" (page "1")))')
out.append(')')
io.open("kali-tank-sensor-v3.kicad_sch","w",encoding="utf-8").write("\n".join(out)+"\n")
print("wrote schematic:", os.path.getsize("kali-tank-sensor-v3.kicad_sch"), "bytes")
print("components:", len(COMPS), " nets:", len(set(NETS.values())))
