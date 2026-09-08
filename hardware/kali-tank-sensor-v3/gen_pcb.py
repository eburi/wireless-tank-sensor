import pcbnew, re, io, os, sys

STOCK = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
LOCAL = os.path.abspath("kali.pretty")
OX, OY = 100.0, 80.0          # board origin in KiCad page coords
BW, BH = 55.0, 52.0           # board size

def V(x, y):  return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
def B(x, y):  return V(OX + x, OY + y)

# ---- placement: ref -> (bx, by, rotation) ----
PLACE = {
 # left column: wire pads, strain-relief hole below each
 "J1": ( 6.0,  7.0,   0), "J2": ( 6.0, 16.0,   0),
 "J3": ( 6.0, 30.0,   0), "J4": ( 6.0, 42.0,   0),
 # top band: 12 V input chain feeding the buck, which sits in the top-right corner
 # so its right-hand proud pads end at the board edge (best iron access)
 "F1": (15.0,  7.0,   0), "D1": (22.0,  7.0, 180), "D2": (22.0, 13.0, 0),
 "C4": (29.0,  7.0,   0), "U3": (42.0,  9.0,   0),
 # XIAO directly under the buck, USB-C flush on the right edge (same 2.5 mm margin
 # as rev 3.0). Top pad row faces the buck 7 mm away, bottom row faces C3/SB1.
 "U1": (42.0, 32.0, 270),
 # analog block: moved as a rigid group next to the sender pads it serves
 "U2": (21.0, 31.0,  90),
 "R1": (18.0, 25.0,   0), "R2": (23.0, 25.0,   0),
 # C1 + pull-ups share one VS_INA bus on their RIGHT-hand pins, so SDA/SCL
 # arrive from the left and never have to cross the bus.
 "C1": (26.0, 31.0, 180), "R6": (26.0, 36.0, 180), "R5": (26.0, 40.0, 180),
 "Q1": (18.0, 36.0,   0), "R3": (11.5, 36.0,   0), "R4": (18.0, 41.0, 0),
 # bottom band: 3V3 bulk caps and the solder bridge under the XIAO's supply pins
 "C2": (30.5, 48.0,   0), "C3": (37.5, 48.0,   0), "SB1":(44.5, 48.0,   0),
}


# ---- read the ERC-verified netlist so the PCB cannot diverge from the schematic ----
src = io.open("net.net", encoding="utf-8").read()
comps = {}
seg = src[src.find("(components"):src.find("(libparts")]
for m in re.finditer(r'\(comp\b', seg):
    d = 0; j = m.start()
    while j < len(seg):
        if seg[j] == '(': d += 1
        elif seg[j] == ')':
            d -= 1
            if d == 0: break
        j += 1
    blk = seg[m.start():j+1]
    ref = re.search(r'\(ref "([^"]+)"\)', blk)
    val = re.search(r'\(value "([^"]*)"\)', blk)
    fpn = re.search(r'\(footprint "([^"]+)"\)', blk)
    if ref and fpn and not ref.group(1).startswith("#"):
        comps[ref.group(1)] = (val.group(1) if val else "", fpn.group(1))

nets = {}
nseg = src[src.find("(nets"):]
for m in re.finditer(r'\(net\b', nseg):
    d = 0; j = m.start()
    while j < len(nseg):
        if nseg[j] == '(': d += 1
        elif nseg[j] == ')':
            d -= 1
            if d == 0: break
        j += 1
    blk = nseg[m.start():j+1]
    nm = re.search(r'\(name "([^"]*)"', blk)
    if not nm: continue
    nodes = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', blk)
    if nodes: nets[nm.group(1)] = nodes

board = pcbnew.NewBoard("kali-tank-sensor-v3.kicad_pcb")

# 2-layer stack
ds = board.GetDesignSettings()
board.SetCopperLayerCount(4)

# ---- board outline ----
pts = [(0,0),(BW,0),(BW,BH),(0,BH)]
_keep = []
for i in range(4):
    sh = pcbnew.PCB_SHAPE(board)
    sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
    sh.SetStart(B(*pts[i])); sh.SetEnd(B(*pts[(i+1) % 4]))
    sh.SetLayer(pcbnew.Edge_Cuts); sh.SetWidth(pcbnew.FromMM(0.15))
    board.Add(sh); sh.thisown = False; _keep.append(sh)

# ---- nets ----
netinfo = {}
for name in nets:
    if name.startswith("unconnected-"): continue
    n = pcbnew.NETINFO_ITEM(board, name)
    board.Add(n); netinfo[name] = n

pad_net = {}
for name, nodes in nets.items():
    if name.startswith("unconnected-"): continue
    for ref, pin in nodes: pad_net[(ref, pin)] = name

# ---- footprints ----
placed = {}
for ref, (val, fpid) in sorted(comps.items()):
    lib, fpname = fpid.split(":")
    libpath = LOCAL if lib == "kali" else STOCK + lib + ".pretty"
    fp = pcbnew.FootprintLoad(libpath, fpname)
    if fp is None: sys.exit(f"footprint load failed: {fpid}")
    bx, by, rot = PLACE[ref]
    board.Add(fp)
    fp.SetPosition(B(bx, by))
    if rot: fp.SetOrientationDegrees(rot)
    fp.SetReference(ref); fp.SetValue(val)
    fp.Reference().SetLayer(pcbnew.F_SilkS)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
    fp.Value().SetLayer(pcbnew.F_Fab); fp.Value().SetVisible(False)
    for pad in fp.Pads():
        key = (ref, pad.GetNumber())
        if key in pad_net: pad.SetNet(netinfo[pad_net[key]])
    placed[ref] = fp


# ---- tidy reference text: keep it on the board, near its part ----
REF_OFF = {"U1": (0, 0), "U3": (0, 0), "SB1": (0, -2.6), "U2": (0, -3.4)}
for ref, fp in placed.items():
    dx, dy = REF_OFF.get(ref, (0.0, -2.2))
    pos = fp.GetPosition()
    fp.Reference().SetPosition(pcbnew.VECTOR2I(pos.x + pcbnew.FromMM(dx),
                                               pos.y + pcbnew.FromMM(dy)))
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
    fp.Reference().SetTextThickness(pcbnew.FromMM(0.12))

# ---- design rules: comfortably inside PCBWay's cheapest (6/6 mil) capability ----
ds.SetCopperLayerCount(4)
ds.m_TrackMinWidth      = pcbnew.FromMM(0.25)
ds.m_ViasMinSize        = pcbnew.FromMM(0.6)
ds.m_MinThroughDrill    = pcbnew.FromMM(0.3)
ds.m_HoleToHoleMin      = pcbnew.FromMM(0.5)
ds.m_HoleClearance      = pcbnew.FromMM(0.25)
# 0.15 mm min clearance: the only gaps that tight are inside the INA238's own
# MSOP-10 land (0.5 mm pitch, 0.35 mm pads). Tracks stay at 0.2 mm or wider.
ds.m_MinClearance       = pcbnew.FromMM(0.15)
ds.m_CopperEdgeClearance= pcbnew.FromMM(0.3)
ds.m_MinSilkTextHeight  = pcbnew.FromMM(0.7)
try:
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(pcbnew.FromMM(0.15)); nc.SetTrackWidth(pcbnew.FromMM(0.25))
    nc.SetViaDiameter(pcbnew.FromMM(0.7)); nc.SetViaDrill(pcbnew.FromMM(0.35))
    print("netclass: clearance 0.15 / track 0.25 / via 0.7-0.35 mm")
except Exception as e:
    print("netclass note:", e)

# ---- silkscreen ----
def silk(txt, x, y, size=1.0, layer=pcbnew.F_SilkS, thick=0.15, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt); t.SetPosition(B(x, y)); t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
    t.SetTextThickness(pcbnew.FromMM(thick))
    if angle: t.SetTextAngleDegrees(angle)
    board.Add(t); t.thisown = False; _keep.append(t); return t

silk("KALI TANK SENSOR  rev 3", 22.0, 50.8, 1.0)
silk("12V+",  10.6,  7.0, 0.9)
silk("12V-",  11.2, 16.0, 0.9)
silk("SND A", 11.5, 30.0, 0.9)
silk("SND B", 11.5, 42.0, 0.9)
silk("OPEN BEFORE USB", 45.0, 50.9, 0.7)
silk("VERIFY DC/DC PINOUT", 42.0, 17.3, 0.7)
silk("USB", 52.2, 45.0, 0.9)


# ---- GND pours: solid on the bottom, and a top pour that stitches the many
#      GND pads without a rat's nest of hand-routed returns ----
def add_zone(layer, netname, inset):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netinfo[netname])
    z.SetIsFilled(True)
    z.SetLocalClearance(pcbnew.FromMM(0.25))
    z.SetMinThickness(pcbnew.FromMM(0.2))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.3))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.4))
    o = z.Outline()
    o.NewOutline()
    for (px, py) in [(inset, inset), (BW-inset, inset), (BW-inset, BH-inset), (inset, BH-inset)]:
        o.Append(B(px, py).x, B(px, py).y)
    board.Add(z); z.thisown = False; _keep.append(z)
    return z

# 4-layer stack: F.Cu signal / In1 solid GND / In2 3V3 / B.Cu signal.
# The GND plane sits directly under the analog front end and the switcher.
add_zone(pcbnew.In1_Cu, "GND",  0.6)
add_zone(pcbnew.In2_Cu, "+3V3", 0.6)
add_zone(pcbnew.F_Cu,   "GND",  0.6)
add_zone(pcbnew.B_Cu,   "GND",  0.6)

# keep the top pour out from under the XIAO: its underside carries an exposed
# thermal pad and the JTAG/battery pads, with only solder mask in between
ko = pcbnew.ZONE(board)
ko.SetLayer(pcbnew.F_Cu)
ko.SetIsRuleArea(True)
ko.SetDoNotAllowZoneFills(True)
ko.SetDoNotAllowTracks(True)
ko.SetDoNotAllowVias(True)
oo = ko.Outline(); oo.NewOutline()
for (px, py) in [(35.0, 26.5), (49.0, 26.5), (49.0, 37.5), (35.0, 37.5)]:
    oo.Append(B(px, py).x, B(px, py).y)
board.Add(ko); ko.thisown = False; _keep.append(ko)

# keep the pours away from the non-plated strain-relief holes
import math
for (hx, hy) in [(6.0, 10.6), (6.0, 19.6), (6.0, 33.6), (6.0, 45.6)]:
    ka = pcbnew.ZONE(board)
    ka.SetLayer(pcbnew.F_Cu)
    ka.SetLayerSet(pcbnew.LSET.AllCuMask())
    ka.SetIsRuleArea(True)
    ka.SetDoNotAllowZoneFills(True)
    ka.SetDoNotAllowTracks(False); ka.SetDoNotAllowVias(False)
    ka.SetDoNotAllowPads(False);   ka.SetDoNotAllowFootprints(False)
    oc = ka.Outline(); oc.NewOutline()
    for k in range(12):
        a = 2 * math.pi * k / 12
        oc.Append(B(hx + 1.7 * math.cos(a), hy + 1.7 * math.sin(a)).x,
                  B(hx + 1.7 * math.cos(a), hy + 1.7 * math.sin(a)).y)
    board.Add(ka); ka.thisown = False; _keep.append(ka)

try:
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print("zones filled:", board.GetAreaCount())
except Exception as e:
    print("zone fill note:", e)

pcbnew.SaveBoard("kali-tank-sensor-v3.kicad_pcb", board)
print(f"placed {len(placed)} footprints, {len(netinfo)} nets, board {BW}x{BH} mm")
for ref in sorted(placed):
    fp = placed[ref]; bb = fp.GetBoundingBox()
    print(f"  {ref:<4} {comps[ref][0][:16]:<17} "
          f"x {pcbnew.ToMM(bb.GetLeft())-OX:6.2f}..{pcbnew.ToMM(bb.GetRight())-OX:6.2f}  "
          f"y {pcbnew.ToMM(bb.GetTop())-OY:6.2f}..{pcbnew.ToMM(bb.GetBottom())-OY:6.2f}")

# ============================ ROUTING ============================
PADXY = {}
for ref, fp in placed.items():
    for pad in fp.Pads():
        if pad.GetNumber():
            q = pad.GetPosition()
            PADXY[(ref, pad.GetNumber())] = (round(pcbnew.ToMM(q.x) - OX, 3),
                                             round(pcbnew.ToMM(q.y) - OY, 3))
def P(ref, pad): return PADXY[(ref, pad)]
F, Bt = pcbnew.F_Cu, pcbnew.B_Cu
ROUTES, VIAS = [], []
def R(net, layer, w, pts): ROUTES.append((net, layer, w, pts))
def VIA(net, x, y): VIAS.append((net, x, y))

# ---- 12 V input chain --------------------------------------------------
R("V12_IN", F, 0.5, [P("J1","1"), P("F1","1")])
R("V12_F",  F, 0.5, [P("F1","2"), P("D1","2")])
R("V12_F",  F, 0.4, [(19.85, 7.0), P("D2","1")])
R("V12_P",  F, 0.5, [P("D1","1"), P("C4","1"), (28.05, 13.25), P("U3","1")])

# ---- GND / 3V3 drop straight into their planes -------------------------
GNDV = [("C1","2", 25.05, 33.0), ("C2","2", 33.0, 48.0), ("C3","2", 40.5, 48.0),
        ("C4","2", 31.6,  7.0), ("D2","2", 26.4, 13.0), ("J2","1",  9.0, 16.0),
        ("Q1","2", 17.062,38.6),("R4","2", 18.912,43.2),("U1","13",47.08,44.0),
        ("U3","2", 31.3,  4.75),("U3","4", 53.5,  4.75)]
for ref, pad, vx, vy in GNDV:
    R("GND", F, 0.35, [P(ref, pad), (vx, vy)]); VIA("GND", vx, vy)
R("GND", F, 0.25, [P("U2","7"), (21.5, 30.6)]); VIA("GND", 21.5, 30.6)
R("GND", F, 0.25, [P("U2","1"), (20.0, 34.9)])
R("GND", F, 0.25, [P("U2","2"), (20.5, 34.2), (20.0, 34.9)])
VIA("GND", 20.0, 34.9)
P3V3 = [("C2","1", 27.5, 48.0), ("C3","1", 34.5, 48.0), ("R1","1", 17.088, 22.5),
        ("SB1","1",42.2, 48.0), ("U3","3", 53.5, 13.25)]
for ref, pad, vx, vy in P3V3:
    R("+3V3", F, 0.4, [P(ref, pad), (vx, vy)]); VIA("+3V3", vx, vy)
R("+3V3", F, 0.25, [P("U2","10"), (20.0, 26.6), (18.6, 26.6)]); VIA("+3V3", 18.6, 26.6)

# ---- analog front end (planar on the top layer) ------------------------
R("SHUNT_LO", F, 0.25, [P("R1","2"), P("R2","1")])
R("SHUNT_LO", F, 0.25, [(20.5, 25.0), P("U2","9")])
R("NODE_A",   F, 0.25, [P("U2","8"), (21.0, 27.2), (23.912, 27.2), P("R2","2")])
R("VS_INA",   F, 0.25, [P("U2","6"), (22.0, 27.9), (26.93, 27.9), (26.93, 40.0)])

# ---- sender cables (short now: the analog block sits next to J3/J4) -----
VIA("NODE_A", 22.0, 27.2)
R("NODE_A", Bt, 0.3, [(22.0, 27.2), (22.0, 29.4), (8.0, 29.4)])
VIA("NODE_A", 8.0, 29.4)
R("NODE_A", F, 0.3, [(8.0, 29.4), (8.0, 30.0), P("J3","1")])
R("NODE_B", F, 0.3, [P("Q1","3"), (20.6, 36.0), (20.6, 44.5)])
VIA("NODE_B", 20.6, 44.5)
R("NODE_B", Bt, 0.3, [(20.6, 44.5), (8.0, 44.5)])
VIA("NODE_B", 8.0, 44.5)
R("NODE_B", F, 0.3, [(8.0, 44.5), (8.0, 42.0), P("J4","1")])

# ---- I2C: SDA turns lower than SCL, so the pair is planar ---------------
R("SDA", F, 0.25, [P("U2","4"), (21.5, 40.0), P("R5","2")])
R("SCL", F, 0.25, [P("U2","5"), (22.0, 36.0), P("R6","2")])
# Both hop to the bottom layer to cross the VS_INA bus, run up to the band
# between the buck and the XIAO, and come back up into the top pad row.
R("SDA", F, 0.25, [(21.5, 40.0), (21.5, 42.0)]); VIA("SDA", 21.5, 42.0)
R("SDA", Bt, 0.25, [(21.5, 42.0), (23.0, 42.0), (23.0, 19.0), (39.46, 19.0)])
VIA("SDA", 39.46, 19.0)
R("SDA", F, 0.25, [(39.46, 19.0), (39.46, 22.5)])
R("SCL", F, 0.25, [(24.5, 36.0), (24.5, 38.0)]); VIA("SCL", 24.5, 38.0)
R("SCL", Bt, 0.25, [(24.5, 38.0), (26.0, 38.0), (26.0, 20.0), (36.92, 20.0)])
VIA("SCL", 36.92, 20.0)
R("SCL", F, 0.25, [(36.92, 20.0), (36.92, 22.5)])

# ---- gate network + MEAS_EN (entirely on the top layer) -----------------
R("GATE", F, 0.25, [P("R3","2"), (14.5, 36.0), (14.5, 33.5), (17.062, 33.5), P("Q1","1")])
R("GATE", F, 0.25, [(14.5, 36.0), (14.5, 41.0), P("R4","1")])
# MEAS_EN leaves R3 to the left, runs up beside the wire pads and across the
# band above the XIAO's top row, no vias.
R("MEAS_EN", F, 0.25, [P("R3","1"), (9.2, 36.0), (9.2, 18.2), (47.08, 18.2), (47.08, 22.5)])

# ---- MCU supply ---------------------------------------------------------
R("VS_INA", F, 0.25, [(26.93, 40.0), (26.93, 43.0), (42.0, 43.0), (42.0, 41.0)])
R("+3V3_MCU", F, 0.4, [P("SB1","2"), (44.54, 46.5), (44.54, 41.0)])

def add_track(net, layer, w, a, b):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(B(*a)); t.SetEnd(B(*b))
    t.SetWidth(pcbnew.FromMM(w)); t.SetLayer(layer)
    t.SetNet(netinfo[net]); board.Add(t); t.thisown = False; _keep.append(t)
for net, layer, w, pts in ROUTES:
    for i in range(len(pts) - 1):
        if pts[i] != pts[i+1]: add_track(net, layer, w, pts[i], pts[i+1])
for net, vx, vy in VIAS:
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(B(vx, vy))
    v.SetWidth(pcbnew.FromMM(0.7)); v.SetDrill(pcbnew.FromMM(0.35))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(netinfo[net]); board.Add(v); v.thisown = False; _keep.append(v)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard("kali-tank-sensor-v3.kicad_pcb", board)
print(f"routed: {sum(len(p)-1 for _,_,_,p in ROUTES)} segments, {len(VIAS)} vias, 4 layers")
