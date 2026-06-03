# ==============================================================
# Create Tracked Cameras - Blender Add-on  v1.13.0
# Compatible: Blender 5.0+
# ==============================================================

bl_info = {
    "name": "Create Tracked Cameras",
    "author": "philipischneider",
    "version": (1, 19, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Shift+A > Tracked Camera | N-panel > TCamera",
    "description": (
        "Creates cameras pre-configured with Track To, Follow Path, "
        "Dolly, Crane, and Vertigo (Dolly Zoom) effects"
    ),
    "warning": "",
    "doc_url": "https://github.com/philipischneider/create-tracked-cameras",
    "category": "Camera",
}

import re
import math
import configparser

import bpy
from bpy.props import (BoolProperty, FloatProperty, IntProperty,
                       EnumProperty, StringProperty, PointerProperty)
from bpy.types import AddonPreferences, Operator, PropertyGroup, Panel
from mathutils import Vector
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────

ADDON_ID     = "bl_ext.user_default.create_tracked_cameras"
INI_FILENAME = "create_tracked_cameras.ini"

_DEFAULTS = {
    "target_empty_size":    0.010,
    "camera_display_size":  0.250,
    "dof_empty_size":       0.010,
    "camera_distance":      0.050,
    "clip_start":           0.001,
    "clip_end":             2.000,
    "use_collection":       False,
    "circle_radius":        0.250,
    "target_circle_radius": 0.100,
    "spline_resolution":    64,
    "dof_fstop":            2.8,
    "dof_blades":           0,
    "dof_rotation":         0.0,
    "dof_ratio":            1.0,
}
_FLOAT_KEYS = ("target_empty_size","camera_display_size","dof_empty_size",
               "camera_distance","clip_start","clip_end",
               "circle_radius","target_circle_radius",
               "dof_fstop","dof_rotation","dof_ratio")
_INT_KEYS   = ("spline_resolution","dof_blades")
_BOOL_KEYS  = ("use_collection",)


# ── INI helpers ───────────────────────────────────────────────

def get_ini_path():
    return Path.home() / INI_FILENAME

def load_ini_values():
    result = dict(_DEFAULTS)
    ini_path = get_ini_path()
    if not ini_path.exists():
        return result
    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")
    if "Settings" not in config:
        return result
    for key in _FLOAT_KEYS:
        try:    result[key] = float(config["Settings"][key])
        except: pass
    for key in _INT_KEYS:
        try:    result[key] = int(config["Settings"][key])
        except: pass
    for key in _BOOL_KEYS:
        try:    result[key] = config.getboolean("Settings", key, fallback=_DEFAULTS[key])
        except: pass
    return result

def save_ini_values(values):
    config = configparser.ConfigParser()
    s = {}
    for k in _FLOAT_KEYS: s[k] = f"{values[k]:.6f}"
    for k in _INT_KEYS:   s[k] = str(int(values[k]))
    for k in _BOOL_KEYS:  s[k] = "1" if values[k] else "0"
    config["Settings"] = s
    with open(get_ini_path(), "w", encoding="utf-8") as f:
        config.write(f)


# ── Rig PropertyGroup ─────────────────────────────────────────

class CTCRigProperties(PropertyGroup):
    rig_type: EnumProperty(
        name="Rig Type",
        items=[
            ('NONE',        "—",            ""),
            ('STATIC',      "Static",       ""),
            ('CIRCLE',      "Circle",       ""),
            ('DUAL_CIRCLE', "Dual Circle",  ""),
            ('HELIX',       "Helix",        ""),
            ('DUAL_HELIX',  "Dual Helix",   ""),
            ('DOLLY',       "Dolly",        ""),
            ('CRANE',       "Crane",        ""),
            ('VERTIGO',     "Vertigo",      ""),
            ('HANDHELD',    "Handheld",     ""),
        ],
        default='NONE',
    )

    # ── Orbit / Helix path ─────────────────────────────────────
    radius: FloatProperty(
        name="Radius",
        description="Raio do path da câmera (circle/helix início; crane = distância)",
        default=0.250, min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    radius_end: FloatProperty(
        name="Radius End",  default=0.100,
        min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    height: FloatProperty(
        name="Height",  default=0.100,
        min=0.0, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    dof_radius: FloatProperty(
        name="DoF Radius",  default=0.100,
        min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    dof_radius_end: FloatProperty(
        name="DoF Radius End",  default=0.040,
        min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )

    # ── Dolly / Vertigo path ───────────────────────────────────
    distance_start: FloatProperty(
        name="Distância Inicial",
        description="Distância câmera–target no início do path",
        default=0.300, min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    distance_end: FloatProperty(
        name="Distância Final",
        description="Distância câmera–target no final do path",
        default=0.100, min=0.0001, soft_max=1000.0, unit="LENGTH", precision=4,
    )
    height_start: FloatProperty(
        name="Altura Inicial",
        description="Altura Z da câmera no início",
        default=0.0, soft_min=-10.0, soft_max=10.0, unit="LENGTH", precision=4,
    )
    height_end: FloatProperty(
        name="Altura Final",
        description="Altura Z da câmera no final",
        default=0.0, soft_min=-10.0, soft_max=10.0, unit="LENGTH", precision=4,
    )

    # ── Crane arc ─────────────────────────────────────────────
    elevation_start: FloatProperty(
        name="Elevação Inicial",
        description="0° = câmera no plano horizontal; 90° = acima do target",
        default=0.0, min=-math.pi / 2, max=math.pi / 2,
        subtype='ANGLE', unit='ROTATION',
    )
    elevation_end: FloatProperty(
        name="Elevação Final",
        description="Elevação final do arco de crane",
        default=math.pi / 2, min=-math.pi / 2, max=math.pi / 2,
        subtype='ANGLE', unit='ROTATION',
    )

    # ── Crane azimuth (deslocamento lateral) ──────────────────
    azimuth_start: FloatProperty(
        name="Azimute Inicial",
        description="Posição angular lateral no início do arco (0 = eixo Y)",
        default=0.0, min=-math.pi, max=math.pi,
        subtype='ANGLE', unit='ROTATION',
    )
    azimuth_end: FloatProperty(
        name="Azimute Final",
        description="Deslocamento lateral no ponto final do crane",
        default=0.0, min=-math.pi, max=math.pi,
        subtype='ANGLE', unit='ROTATION',
    )

    # ── Handheld arc ───────────────────────────────────────────
    arc_angle: FloatProperty(
        name="Abertura do Arco",
        description="Ângulo total do arco horizontal percorrido pela câmera",
        default=0.5236, min=0.0873, max=math.pi,
        subtype='ANGLE', unit='ROTATION',
    )
    hh_pos_strength: FloatProperty(
        name="Noise de Posição",
        description="Amplitude do jitter de posição baked no path",
        default=0.0003, min=0.0, soft_max=0.005,
        unit='LENGTH', precision=4,
    )
    hh_rot_strength: FloatProperty(
        name="Amplitude de Roll",
        description="Amplitude do ruído de roll da câmera",
        default=0.003, min=0.0, soft_max=math.radians(10),
        subtype='ANGLE', unit='ROTATION',
    )
    hh_rot_scale: FloatProperty(
        name="Período de Roll (frames)",
        description="Período do noise de roll em frames: 15 = ciclo completo a cada ~15 frames",
        default=15.0, min=0.5, soft_max=200.0, precision=1,
    )
    hh_target_strength: FloatProperty(
        name="Noise de Target",
        description="Amplitude do jitter na posição do target (pan/tilt indireto)",
        default=0.0001, min=0.0, soft_max=0.002,
        unit='LENGTH', precision=4,
    )
    hh_noise_scale: FloatProperty(
        name="Escala espacial (path)",
        description="Escala do noise baked no path: valores maiores = ondulação mais esparsa no espaço",
        default=12.0, min=0.1, soft_max=100.0, precision=1,
    )
    hh_target_scale: FloatProperty(
        name="Período (frames)",
        description="Período do noise no target em frames: 8 = ciclo completo a cada ~8 frames",
        default=8.0, min=0.5, soft_max=200.0, precision=1,
    )
    hh_phase: FloatProperty(
        name="Phase (Seed)",
        description="Semente do ruído — muda o padrão sem alterar intensidade",
        default=0.0, precision=2,
    )

    # ── Vertigo driver ─────────────────────────────────────────
    base_distance: FloatProperty(
        name="Distância de Base",
        description=(
            "Distância de referência: com a câmera aqui, o enquadramento do "
            "subject corresponde à focal de base"
        ),
        default=0.150, min=0.0001, soft_max=100.0, unit="LENGTH", precision=4,
    )
    base_lens: FloatProperty(
        name="Focal de Base (mm)",
        description="Comprimento focal de referência usado na distância de base",
        default=50.0, min=1.0, max=5000.0, precision=1,
    )
    magnitude: FloatProperty(
        name="Magnitude",
        description="0 = sem efeito · 1 = vertigo puro · >1 = exagerado",
        default=1.0, min=0.0, soft_max=3.0, precision=3,
    )

    # ── Animation ─────────────────────────────────────────────
    has_animation: BoolProperty(default=False)
    frame_start: IntProperty(name="Frame Start", default=0)
    frame_end:   IntProperty(name="Frame End",   default=250)
    ease_start: EnumProperty(
        name="Início",
        items=[('LINEAR','Linear',""),('EASE_IN','Ease In',"")],
        default='LINEAR',
    )
    ease_end: EnumProperty(
        name="Final",
        items=[('LINEAR','Linear',""),('EASE_OUT','Ease Out',"")],
        default='EASE_OUT',
    )

    # ── Linked object names ────────────────────────────────────
    path_name:       StringProperty()
    dof_path_name:   StringProperty()
    target_name:     StringProperty()
    dof_name:        StringProperty()
    follow_cname:    StringProperty()
    dof_follow_cname: StringProperty()
    follow_empty_name: StringProperty()  # handheld: empty que carrega Follow Path + Damped Track


# ── Preferences ───────────────────────────────────────────────

class CreateTrackedCamerasPreferences(AddonPreferences):
    bl_idname = ADDON_ID

    target_empty_size:    FloatProperty(name="Target Empty Size",    default=_DEFAULTS["target_empty_size"],    min=0.0001, soft_max=10.0,    unit="LENGTH", precision=4)
    camera_display_size:  FloatProperty(name="Camera Display Size",  default=_DEFAULTS["camera_display_size"],  min=0.0001, soft_max=10.0,    unit="LENGTH", precision=4)
    dof_empty_size:       FloatProperty(name="DoF Empty Size",       default=_DEFAULTS["dof_empty_size"],       min=0.0001, soft_max=10.0,    unit="LENGTH", precision=4)
    camera_distance:      FloatProperty(name="Camera Distance",      default=_DEFAULTS["camera_distance"],      min=0.0001, soft_max=1000.0,  unit="LENGTH", precision=4)
    clip_start:           FloatProperty(name="Clip Start",           default=_DEFAULTS["clip_start"],           min=0.0001, soft_max=100.0,   unit="LENGTH", precision=4)
    clip_end:             FloatProperty(name="Clip End",             default=_DEFAULTS["clip_end"],             min=0.001,  soft_max=10000.0, unit="LENGTH", precision=4)
    use_collection:       BoolProperty( name="Create Collection per Camera",   default=_DEFAULTS["use_collection"])
    circle_radius:        FloatProperty(name="Circle Radius",        default=_DEFAULTS["circle_radius"],        min=0.0001, soft_max=1000.0,  unit="LENGTH", precision=4)
    target_circle_radius: FloatProperty(name="Target Circle Radius", default=_DEFAULTS["target_circle_radius"], min=0.0001, soft_max=1000.0,  unit="LENGTH", precision=4)
    spline_resolution:    IntProperty(  name="Spline Resolution",    default=_DEFAULTS["spline_resolution"],    min=2, max=1024)
    dof_fstop:            FloatProperty(name="Aperture F-Stop",      default=_DEFAULTS["dof_fstop"],           min=0.0, soft_max=128.0, precision=2)
    dof_blades:           IntProperty(  name="Aperture Blades",      default=_DEFAULTS["dof_blades"],          min=0, max=16)
    dof_rotation:         FloatProperty(name="Aperture Rotation",    default=_DEFAULTS["dof_rotation"],        min=-3.14159, max=3.14159, subtype="ANGLE", precision=3)
    dof_ratio:            FloatProperty(name="Aperture Ratio",       default=_DEFAULTS["dof_ratio"],           min=0.0001, soft_max=2.0, precision=3)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        split = box.split(factor=0.2)
        split.label(text="Config file:", icon="FILE_TEXT")
        split.label(text=str(get_ini_path()))
        layout.separator()
        box = layout.box()
        box.label(text="Tamanhos e distâncias:", icon="OBJECT_DATA")
        col = box.column(align=True)
        col.prop(self, "target_empty_size"); col.prop(self, "dof_empty_size")
        col.prop(self, "camera_display_size"); col.prop(self, "camera_distance")
        layout.separator()
        box = layout.box()
        box.label(text="Clip planes:", icon="CAMERA_DATA")
        col = box.column(align=True)
        col.prop(self, "clip_start"); col.prop(self, "clip_end")
        layout.separator()
        box = layout.box()
        box.label(text="Organização:", icon="OUTLINER_COLLECTION")
        box.prop(self, "use_collection")
        layout.separator()
        box = layout.box()
        layout.separator()
        box = layout.box()
        box.label(text="Depth of Field (Aperture):", icon="CAMERA_DATA")
        col = box.column(align=True)
        col.prop(self, "dof_fstop"); col.prop(self, "dof_blades")
        col.prop(self, "dof_rotation"); col.prop(self, "dof_ratio")
        layout.separator()
        box = layout.box()
        box.label(text="Follow Path:", icon="CURVE_BEZCIRCLE")
        col = box.column(align=True)
        col.prop(self, "circle_radius"); col.prop(self, "target_circle_radius")
        col.prop(self, "spline_resolution")
        layout.separator()
        row = layout.row(align=True)
        row.operator("preferences.ctc_save_ini", icon="EXPORT")
        row.operator("preferences.ctc_load_ini", icon="IMPORT")


class PREFERENCES_OT_ctc_save_ini(Operator):
    bl_idname = "preferences.ctc_save_ini"; bl_label = "Save to INI"
    def execute(self, context):
        p = context.preferences.addons[ADDON_ID].preferences
        save_ini_values({"target_empty_size":p.target_empty_size,"camera_display_size":p.camera_display_size,
                         "dof_empty_size":p.dof_empty_size,"camera_distance":p.camera_distance,
                         "clip_start":p.clip_start,"clip_end":p.clip_end,"use_collection":p.use_collection,
                         "circle_radius":p.circle_radius,"target_circle_radius":p.target_circle_radius,
                         "spline_resolution":p.spline_resolution,
                         "dof_fstop":p.dof_fstop,"dof_blades":p.dof_blades,
                         "dof_rotation":p.dof_rotation,"dof_ratio":p.dof_ratio})
        self.report({"INFO"}, f"Saved → {get_ini_path()}"); return {"FINISHED"}

class PREFERENCES_OT_ctc_load_ini(Operator):
    bl_idname = "preferences.ctc_load_ini"; bl_label = "Load from INI"
    def execute(self, context):
        v = load_ini_values()
        p = context.preferences.addons[ADDON_ID].preferences
        p.target_empty_size=v["target_empty_size"]; p.camera_display_size=v["camera_display_size"]
        p.dof_empty_size=v["dof_empty_size"]; p.camera_distance=v["camera_distance"]
        p.clip_start=v["clip_start"]; p.clip_end=v["clip_end"]; p.use_collection=v["use_collection"]
        p.circle_radius=v["circle_radius"]; p.target_circle_radius=v["target_circle_radius"]
        p.spline_resolution=v["spline_resolution"]
        p.dof_fstop=v["dof_fstop"]; p.dof_blades=v["dof_blades"]
        p.dof_rotation=v["dof_rotation"]; p.dof_ratio=v["dof_ratio"]
        self.report({"INFO"}, f"Loaded ← {get_ini_path()}"); return {"FINISHED"}


# ── Shared helpers ────────────────────────────────────────────

def _next_camera_number():
    used = set()
    pat  = re.compile(r"^TCamera_(\d+)$")
    for obj in bpy.data.objects:
        m = pat.match(obj.name)
        if m: used.add(int(m.group(1)))
    n = 1
    while n in used: n += 1
    return n

def _iter_action_fcurves(obj):
    ad = obj.animation_data
    if not ad or not ad.action: return
    action = ad.action
    if hasattr(action, "layers"):
        slot = getattr(ad, "action_slot", None)
        for layer in action.layers:
            for strip in layer.strips:
                try:    cb = strip.channelbag(slot) if slot is not None else None
                except: cb = None
                if cb is not None: yield from cb.fcurves
        return
    if hasattr(action, "fcurves"): yield from action.fcurves

def _clear_constraint_keyframes(obj, data_path):
    ad = obj.animation_data
    if not ad or not ad.action: return
    action = ad.action
    if hasattr(action, "layers"):
        slot = getattr(ad, "action_slot", None)
        for layer in action.layers:
            for strip in layer.strips:
                try:    cb = strip.channelbag(slot) if slot is not None else None
                except: cb = None
                if cb is not None:
                    for fc in [f for f in cb.fcurves if f.data_path == data_path]:
                        cb.fcurves.remove(fc)
    else:
        if hasattr(action, "fcurves"):
            for fc in [f for f in action.fcurves if f.data_path == data_path]:
                action.fcurves.remove(fc)

def _apply_easing(obj, data_path, ease_start='LINEAR', ease_end='EASE_OUT'):
    for fcurve in _iter_action_fcurves(obj):
        if fcurve.data_path != data_path: continue
        kps = fcurve.keyframe_points
        if len(kps) < 2: continue
        kp0, kp1 = kps[0], kps[1]
        if ease_start == 'LINEAR' and ease_end == 'LINEAR':
            kp0.interpolation = kp1.interpolation = 'LINEAR'
            fcurve.update(); continue
        kp0.interpolation = kp1.interpolation = 'BEZIER'
        h = (kp1.co.x - kp0.co.x) * 0.35
        if ease_start == 'LINEAR':
            kp0.handle_right_type = kp0.handle_left_type = 'VECTOR'
        else:
            kp0.handle_right_type = kp0.handle_left_type = 'FREE'
            kp0.handle_right = Vector((kp0.co.x + h, kp0.co.y))
            kp0.handle_left  = Vector((kp0.co.x - h, kp0.co.y))
        if ease_end == 'LINEAR':
            kp1.handle_left_type = kp1.handle_right_type = 'VECTOR'
        else:
            kp1.handle_left_type  = kp1.handle_right_type = 'FREE'
            kp1.handle_left  = Vector((kp1.co.x - h, kp1.co.y))
            kp1.handle_right = Vector((kp1.co.x + h, kp1.co.y))
        fcurve.update()

def _create_follow_path_animation(obj, constraint_name, frame_start, frame_end,
                                   ease_start='LINEAR', ease_end='EASE_OUT'):
    if obj.animation_data is None: obj.animation_data_create()
    dp = f'constraints["{constraint_name}"].offset'
    _clear_constraint_keyframes(obj, dp)
    obj.constraints[constraint_name].offset = 0.0
    obj.keyframe_insert(data_path=dp, frame=frame_start)
    obj.constraints[constraint_name].offset = -100.0
    obj.keyframe_insert(data_path=dp, frame=frame_end)
    _apply_easing(obj, dp, ease_start, ease_end)

def _prepare_collection(n, prefs, context):
    coll = bpy.data.collections.new(f"TCamera_{n}")
    context.scene.collection.children.link(coll)
    return coll

def _new_camera(n, prefs):
    d = bpy.data.cameras.new(f"TCamera_{n}")
    d.display_size = prefs.camera_display_size
    d.clip_start   = prefs.clip_start
    d.clip_end     = prefs.clip_end
    d.dof.aperture_fstop    = prefs.dof_fstop
    d.dof.aperture_blades   = prefs.dof_blades
    d.dof.aperture_rotation = prefs.dof_rotation
    d.dof.aperture_ratio    = prefs.dof_ratio
    return d

def _new_target(n, prefs, location, coll):
    o = bpy.data.objects.new(f"Target_Camera_{n}", None)
    o.empty_display_type = "PLAIN_AXES"
    o.empty_display_size = prefs.target_empty_size
    o.location = location
    coll.objects.link(o)
    return o

def _new_dof(n, prefs, location, coll):
    o = bpy.data.objects.new(f"DoF_Camera_{n}", None)
    o.empty_display_type = "PLAIN_AXES"
    o.empty_display_size = prefs.dof_empty_size
    o.location = location
    coll.objects.link(o)
    return o

def _add_track_to(cam_obj, target_obj):
    t = cam_obj.constraints.new(type="TRACK_TO")
    t.target = target_obj; t.track_axis = "TRACK_NEGATIVE_Z"; t.up_axis = "UP_Y"
    return t

def _add_damped_track(cam_obj, target_obj):
    """Damped Track: aponta ao target sem fixar eixo 'up' — roll livre para FCurves."""
    t = cam_obj.constraints.new(type="DAMPED_TRACK")
    t.target = target_obj; t.track_axis = "TRACK_NEGATIVE_Z"
    return t

def _add_follow_path(cam_obj, path_obj):
    f = cam_obj.constraints.new(type="FOLLOW_PATH")
    f.target = path_obj; f.use_curve_follow = False
    return f

# ── Curve builders ────────────────────────────────────────────

def _make_bezier_circle(name, radius, location, resolution=64):
    h = radius * (4.0/3.0) * math.tan(math.pi/8.0)
    pts = [
        (( radius,  0,  0),( radius,-h, 0),( radius, h, 0)),
        (( 0, radius,  0),( h, radius, 0),(-h, radius, 0)),
        ((-radius,  0,  0),(-radius, h, 0),(-radius,-h, 0)),
        (( 0,-radius,  0),(-h,-radius, 0),( h,-radius, 0)),
    ]
    c = bpy.data.curves.new(name, "CURVE"); c.dimensions="3D"; c.resolution_u=resolution
    sp = c.splines.new("BEZIER"); sp.bezier_points.add(3); sp.use_cyclic_u=True
    for i,(co,hl,hr) in enumerate(pts):
        bp=sp.bezier_points[i]; bp.co=Vector(co); bp.handle_left=Vector(hl)
        bp.handle_right=Vector(hr); bp.handle_left_type=bp.handle_right_type="FREE"
    o=bpy.data.objects.new(name,c); o.location=location; return o

def _rebuild_circle_spline(path_obj, radius):
    h = radius*(4.0/3.0)*math.tan(math.pi/8.0)
    pts = [
        (( radius, 0,0),( radius,-h,0),( radius, h,0)),
        (( 0, radius,0),( h, radius,0),(-h, radius,0)),
        ((-radius, 0,0),(-radius, h,0),(-radius,-h,0)),
        (( 0,-radius,0),(-h,-radius,0),( h,-radius,0)),
    ]
    sp = path_obj.data.splines[0]
    for i,(co,hl,hr) in enumerate(pts):
        bp=sp.bezier_points[i]; bp.co=Vector(co); bp.handle_left=Vector(hl); bp.handle_right=Vector(hr)
    path_obj.data.update_tag()

def _make_spiral_curve(name, radius_start, radius_end, height, location,
                        n_points=64, resolution=64):
    c=bpy.data.curves.new(name,"CURVE"); c.dimensions="3D"; c.resolution_u=resolution
    sp=c.splines.new("NURBS"); sp.points.add(n_points-1)
    sp.use_cyclic_u=False; sp.order_u=4; sp.use_endpoint_u=True
    for i in range(n_points):
        t=i/(n_points-1); ang=2*math.pi*t; r=radius_start+(radius_end-radius_start)*t
        sp.points[i].co=(r*math.cos(ang),r*math.sin(ang),height*t,1.0)
    o=bpy.data.objects.new(name,c); o.location=location; return o

def _rebuild_helix_spline(path_obj, radius_start, radius_end, height):
    sp=path_obj.data.splines[0]; n=len(sp.points)
    for i in range(n):
        t=i/(n-1); ang=2*math.pi*t; r=radius_start+(radius_end-radius_start)*t
        sp.points[i].co=(r*math.cos(ang),r*math.sin(ang),height*t,1.0)
    path_obj.data.update_tag()

def _make_dolly_path(name, distance_start, distance_end, height_start, height_end,
                      location, resolution=64):
    """Path linear ao longo do eixo Y (2 pontos NURBS lineares)."""
    c=bpy.data.curves.new(name,"CURVE"); c.dimensions="3D"; c.resolution_u=resolution
    sp=c.splines.new("NURBS"); sp.points.add(1)
    sp.use_cyclic_u=False; sp.order_u=2; sp.use_endpoint_u=True
    sp.points[0].co=(0.0, distance_start, height_start, 1.0)
    sp.points[1].co=(0.0, distance_end,   height_end,   1.0)
    o=bpy.data.objects.new(name,c); o.location=location; return o

def _rebuild_dolly_spline(path_obj, distance_start, distance_end, height_start, height_end):
    sp=path_obj.data.splines[0]
    sp.points[0].co=(0.0,distance_start,height_start,1.0)
    sp.points[1].co=(0.0,distance_end,  height_end,  1.0)
    path_obj.data.update_tag()

def _make_handheld_path(name, radius, height, arc_angle, pos_strength, noise_scale, phase,
                         location, n_points=48, resolution=64):
    """Arco parcial horizontal com noise baked nos pontos de controle."""
    import mathutils
    c=bpy.data.curves.new(name,"CURVE"); c.dimensions="3D"; c.resolution_u=resolution
    sp=c.splines.new("NURBS"); sp.points.add(n_points-1)
    sp.use_cyclic_u=False; sp.order_u=min(4,n_points); sp.use_endpoint_u=True
    for i in range(n_points):
        t=i/(n_points-1)
        angle=-arc_angle/2+t*arc_angle
        xb=radius*math.sin(angle); yb=radius*math.cos(angle); zb=height
        # noise perturbation — offsets distintos por eixo para descorrelacionar
        nv=mathutils.Vector((xb*noise_scale+phase, yb*noise_scale+phase, i*0.07))
        nx=mathutils.noise.noise(nv+mathutils.Vector((0,0,0)))*pos_strength
        ny=mathutils.noise.noise(nv+mathutils.Vector((100,0,0)))*pos_strength
        nz=mathutils.noise.noise(nv+mathutils.Vector((0,100,0)))*pos_strength*0.35
        sp.points[i].co=(xb+nx, yb+ny, zb+nz, 1.0)
    o=bpy.data.objects.new(name,c); o.location=location; return o


def _apply_handheld_noise(cam_obj, target_obj, target_strength,
                           target_scale, phase, frame_start, frame_end):
    """Adiciona F-Curve Noise Modifier na posição do target (pan/tilt jitter)."""
    if target_obj:
        if target_obj.animation_data is None: target_obj.animation_data_create()
        target_obj.delta_location = (0.0, 0.0, 0.0)
        for i in range(3):
            target_obj.keyframe_insert(data_path="delta_location", index=i, frame=frame_start)
            target_obj.keyframe_insert(data_path="delta_location", index=i, frame=frame_end)
        phase_offsets=(7.3, 13.7, 21.1); z_scale=0.45
        for fc in _iter_action_fcurves(target_obj):
            if fc.data_path=="delta_location" and fc.array_index in (0,1,2):
                idx=fc.array_index
                mod=fc.modifiers.new('NOISE')
                mod.scale=target_scale
                s=target_strength*(z_scale if idx==2 else 1.0)
                mod.strength=s; mod.phase=phase+phase_offsets[idx]


def _remove_handheld_noise(target_obj):
    """Remove todos os Noise Modifiers de posição do target."""
    if target_obj:
        for fc in _iter_action_fcurves(target_obj):
            if fc.data_path=="delta_location":
                for mod in list(fc.modifiers):
                    if mod.type=='NOISE': fc.modifiers.remove(mod)


def _make_crane_path(name, radius, height_start, height_end, location,
                      azimuth_start=0.0, azimuth_end=0.0,
                      n_points=32, resolution=64):
    """Arco cilíndrico: raio horizontal constante, altura e azimute variáveis."""
    c=bpy.data.curves.new(name,"CURVE"); c.dimensions="3D"; c.resolution_u=resolution
    sp=c.splines.new("NURBS"); sp.points.add(n_points-1)
    sp.use_cyclic_u=False; sp.order_u=min(4,n_points); sp.use_endpoint_u=True
    for i in range(n_points):
        t=i/(n_points-1)
        az=azimuth_start+(azimuth_end-azimuth_start)*t
        h =height_start +(height_end -height_start )*t
        sp.points[i].co=(radius*math.sin(az), radius*math.cos(az), h, 1.0)
    o=bpy.data.objects.new(name,c); o.location=location; return o

def _rebuild_crane_spline(path_obj, radius, height_start, height_end,
                           azimuth_start=0.0, azimuth_end=0.0):
    sp=path_obj.data.splines[0]; n=len(sp.points)
    for i in range(n):
        t=i/(n-1)
        az=azimuth_start+(azimuth_end-azimuth_start)*t
        h =height_start +(height_end -height_start )*t
        sp.points[i].co=(radius*math.sin(az), radius*math.cos(az), h, 1.0)
    path_obj.data.update_tag()

def _setup_vertigo_driver(cam_obj, target_obj):
    """
    Driver em cam_data.lens para o efeito Vertigo (Dolly Zoom).

    Expressão:  f0 * (d0 / max(0.0001, dist_cam_target)) ** mag

    onde dist_cam_target é calculada via variáveis de transformada (mundo),
    d0 = ctc.base_distance  (propriedade na CTCRigProperties),
    f0 = ctc.base_lens,
    mag = ctc.magnitude.
    """
    cam_data = cam_obj.data
    # Remover driver existente antes de recriar
    try: cam_data.driver_remove("lens")
    except: pass

    fc  = cam_data.driver_add("lens")
    drv = fc.driver
    drv.type = 'SCRIPTED'

    def _sprop(name, id_obj, id_type, data_path):
        v=drv.variables.new(); v.name=name; v.type='SINGLE_PROP'
        v.targets[0].id_type=id_type; v.targets[0].id=id_obj
        v.targets[0].data_path=data_path

    def _transform(name, obj, ttype):
        v=drv.variables.new(); v.name=name; v.type='TRANSFORMS'
        v.targets[0].id=obj; v.targets[0].transform_type=ttype
        v.targets[0].transform_space='WORLD_SPACE'

    _sprop('d0',  cam_data, 'CAMERA', 'ctc.base_distance')
    _sprop('f0',  cam_data, 'CAMERA', 'ctc.base_lens')
    _sprop('mag', cam_data, 'CAMERA', 'ctc.magnitude')
    _transform('cx', cam_obj, 'LOC_X'); _transform('cy', cam_obj, 'LOC_Y')
    _transform('cz', cam_obj, 'LOC_Z'); _transform('tx', target_obj, 'LOC_X')
    _transform('ty', target_obj, 'LOC_Y'); _transform('tz', target_obj, 'LOC_Z')

    drv.expression = (
        "f0 * (max(0.0001, "
        "((cx-tx)**2+(cy-ty)**2+(cz-tz)**2)**0.5) / max(0.0001, d0)) ** mag"
    )


# ── Operator: Static Camera ───────────────────────────────────

class OBJECT_OT_add_tracked_camera(Operator):
    bl_idname="object.add_tracked_camera"; bl_label="Static Camera"
    bl_description="Câmera fixa com Track To, target e DoF empty"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof=_new_dof(n,pr,(cur+cur+Vector((0,pr.camera_distance,0)))*0.5,coll)
        cam_data=_new_camera(n,pr)
        cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='STATIC'
        ctc.target_name=tgt.name; ctc.dof_name=dof.name
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=cur+Vector((0,pr.camera_distance,0)); coll.objects.link(cam)
        _add_track_to(cam,tgt)
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Static)"); return {"FINISHED"}


# ── Operator: Orbit Camera ────────────────────────────────────

class OBJECT_OT_add_tracked_path_camera(Operator):
    bl_idname="object.add_tracked_path_camera"; bl_label="Orbit Camera"
    bl_description="Câmera em órbita circular com Track To e DoF"
    bl_options={"REGISTER","UNDO"}
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location); r=pr.circle_radius
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof=_new_dof(n,pr,(cur+cur+Vector((r,0,0)))*0.5,coll)
        path=_make_bezier_circle(f"Path_TCamera_{n}",r,cur,pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='CIRCLE'; ctc.radius=r
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Orbit)"); return {"FINISHED"}


# ── Operator: Orbit Camera + DoF Orbit ───────────────────────

class OBJECT_OT_add_tracked_dual_path_camera(Operator):
    bl_idname="object.add_tracked_dual_path_camera"
    bl_label="Orbit Camera + DoF Orbit"
    bl_description="Câmera em círculo maior, DoF em círculo menor, target fixo"
    bl_options={"REGISTER","UNDO"}
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        rc=pr.circle_radius; rd=pr.target_circle_radius
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll); dof=_new_dof(n,pr,Vector((0,0,0)),coll)
        dof_path=_make_bezier_circle(f"Path_DoF_Camera_{n}",rd,cur,pr.spline_resolution)
        coll.objects.link(dof_path)
        df=_add_follow_path(dof,dof_path)
        cam_path=_make_bezier_circle(f"Path_TCamera_{n}",rc,cur,pr.spline_resolution)
        coll.objects.link(cam_path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='DUAL_CIRCLE'; ctc.radius=rc; ctc.dof_radius=rd
        ctc.target_name=tgt.name; ctc.dof_name=dof.name
        ctc.path_name=cam_path.name; ctc.dof_path_name=dof_path.name
        ctc.dof_follow_cname=df.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,cam_path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
            _create_follow_path_animation(dof,df.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Dual Orbit)"); return {"FINISHED"}


# ── Operator: Helix Camera ────────────────────────────────────

class OBJECT_OT_add_tracked_spiral_camera(Operator):
    bl_idname="object.add_tracked_spiral_camera"; bl_label="Helix Camera"
    bl_description="Câmera em espiral helix (uma volta, muda raio e altura)"
    bl_options={"REGISTER","UNDO"}
    radius_start: FloatProperty(name="Radius Start",default=0.250,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    radius_end:   FloatProperty(name="Radius End",  default=0.100,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height:       FloatProperty(name="Height",      default=0.100,min=0.0,   soft_max=1000.0,unit="LENGTH",precision=4)
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        path=_make_spiral_curve(f"Path_TCamera_{n}",self.radius_start,self.radius_end,
                                 self.height,cur,resolution=pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=tgt
        ctc=cam_data.ctc; ctc.rig_type='HELIX'; ctc.radius=self.radius_start
        ctc.radius_end=self.radius_end; ctc.height=self.height
        ctc.target_name=tgt.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Helix)"); return {"FINISHED"}


# ── Operator: Helix Camera + DoF Helix ───────────────────────

class OBJECT_OT_add_tracked_dual_spiral_camera(Operator):
    bl_idname="object.add_tracked_dual_spiral_camera"
    bl_label="Helix Camera + DoF Helix"
    bl_description="Câmera e DoF em espirais helix concêntricas"
    bl_options={"REGISTER","UNDO"}
    radius_start:        FloatProperty(name="Camera Radius Start",default=0.250,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    radius_end:          FloatProperty(name="Camera Radius End",  default=0.100,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height:              FloatProperty(name="Height",             default=0.100,min=0.0,   soft_max=1000.0,unit="LENGTH",precision=4)
    target_radius_ratio: FloatProperty(name="DoF Radius Ratio",  default=0.3,  min=0.01,  max=0.99,       precision=2)
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        drs=self.radius_start*self.target_radius_ratio
        dre=self.radius_end  *self.target_radius_ratio
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll); dof=_new_dof(n,pr,Vector((0,0,0)),coll)
        dof_path=_make_spiral_curve(f"Path_DoF_Camera_{n}",drs,dre,self.height,cur,
                                    resolution=pr.spline_resolution)
        coll.objects.link(dof_path); df=_add_follow_path(dof,dof_path)
        cam_path=_make_spiral_curve(f"Path_TCamera_{n}",self.radius_start,self.radius_end,
                                    self.height,cur,resolution=pr.spline_resolution)
        coll.objects.link(cam_path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='DUAL_HELIX'
        ctc.radius=self.radius_start; ctc.radius_end=self.radius_end; ctc.height=self.height
        ctc.dof_radius=drs; ctc.dof_radius_end=dre
        ctc.target_name=tgt.name; ctc.dof_name=dof.name
        ctc.path_name=cam_path.name; ctc.dof_path_name=dof_path.name
        ctc.dof_follow_cname=df.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,cam_path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
            _create_follow_path_animation(dof,df.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Dual Helix)"); return {"FINISHED"}


# ── Operator: Dolly Camera ────────────────────────────────────

class OBJECT_OT_add_dolly_camera(Operator):
    bl_idname="object.add_dolly_camera"; bl_label="Dolly Camera"
    bl_description="Câmera em path linear (dolly in/out) com Track To"
    bl_options={"REGISTER","UNDO"}
    distance_start: FloatProperty(name="Distância Inicial",default=0.300,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    distance_end:   FloatProperty(name="Distância Final",  default=0.100,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height_start:   FloatProperty(name="Altura Inicial",   default=0.0,  soft_min=-10.0,soft_max=10.0,unit="LENGTH",precision=4)
    height_end:     FloatProperty(name="Altura Final",     default=0.0,  soft_min=-10.0,soft_max=10.0,unit="LENGTH",precision=4)
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof_loc=cur+Vector((0,(self.distance_start+self.distance_end)*0.5,
                              (self.height_start+self.height_end)*0.5))
        dof=_new_dof(n,pr,dof_loc,coll)
        path=_make_dolly_path(f"Path_TCamera_{n}",self.distance_start,self.distance_end,
                               self.height_start,self.height_end,cur,pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='DOLLY'
        ctc.distance_start=self.distance_start; ctc.distance_end=self.distance_end
        ctc.height_start=self.height_start; ctc.height_end=self.height_end
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Dolly)"); return {"FINISHED"}


# ── Operator: Crane Camera ────────────────────────────────────

class OBJECT_OT_add_crane_camera(Operator):
    bl_idname="object.add_crane_camera"; bl_label="Crane Camera"
    bl_description="Câmera em arco vertical (crane/jib) com Track To"
    bl_options={"REGISTER","UNDO"}
    radius:          FloatProperty(name="Raio horizontal",default=0.250,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height_start:    FloatProperty(name="Altura Inicial", default=0.020,soft_min=-1.0,soft_max=10.0, unit="LENGTH",precision=4)
    height_end:      FloatProperty(name="Altura Final",   default=0.200,soft_min=-1.0,soft_max=10.0, unit="LENGTH",precision=4)
    azimuth_start:   FloatProperty(name="Azimute Inicial",default=0.0,  min=-math.pi,  max=math.pi,  subtype='ANGLE',unit='ROTATION')
    azimuth_end:     FloatProperty(name="Azimute Final",  default=0.0,  min=-math.pi,  max=math.pi,  subtype='ANGLE',unit='ROTATION')
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof_loc=cur+Vector((0,self.radius,(self.height_start+self.height_end)*0.5))
        dof=_new_dof(n,pr,dof_loc,coll)
        path=_make_crane_path(f"Path_TCamera_{n}",self.radius,self.height_start,
                               self.height_end,cur,
                               azimuth_start=self.azimuth_start,azimuth_end=self.azimuth_end,
                               resolution=pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='CRANE'
        ctc.radius=self.radius
        ctc.height_start=self.height_start; ctc.height_end=self.height_end
        ctc.azimuth_start=self.azimuth_start; ctc.azimuth_end=self.azimuth_end
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Crane)"); return {"FINISHED"}


# ── Operator: Vertigo Camera ──────────────────────────────────

class OBJECT_OT_add_vertigo_camera(Operator):
    bl_idname="object.add_vertigo_camera"; bl_label="Vertigo Camera"
    bl_description=(
        "Câmera em dolly com driver de lente: subject mantém tamanho na tela "
        "enquanto background cresce/diminui (Dolly Zoom / Efeito Vertigo)"
    )
    bl_options={"REGISTER","UNDO"}
    distance_start: FloatProperty(name="Distância Inicial",default=0.300,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    distance_end:   FloatProperty(name="Distância Final",  default=0.100,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height_start:   FloatProperty(name="Altura Inicial",   default=0.0,  soft_min=-10.0,soft_max=10.0,unit="LENGTH",precision=4)
    height_end:     FloatProperty(name="Altura Final",     default=0.0,  soft_min=-10.0,soft_max=10.0,unit="LENGTH",precision=4)
    base_distance:  FloatProperty(
        name="Distância de Base",
        description="Distância de referência onde a focal de base enquadra o subject",
        default=0.150,min=0.0001,soft_max=100.0,unit="LENGTH",precision=4,
    )
    base_lens:      FloatProperty(
        name="Focal de Base (mm)",
        description="Focal usada na distância de base — define o enquadramento de referência",
        default=50.0,min=1.0,max=5000.0,precision=1,
    )
    magnitude:      FloatProperty(
        name="Magnitude",
        description="0 = sem efeito · 1 = vertigo puro · >1 = exagerado",
        default=1.0,min=0.0,soft_max=3.0,precision=3,
    )
    create_animation: BoolProperty(name="Create Animation",default=False)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof_loc=cur+Vector((0,(self.distance_start+self.distance_end)*0.5,
                              (self.height_start+self.height_end)*0.5))
        dof=_new_dof(n,pr,dof_loc,coll)
        path=_make_dolly_path(f"Path_TCamera_{n}",self.distance_start,self.distance_end,
                               self.height_start,self.height_end,cur,pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr)
        cam_data.lens=self.base_lens
        cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='VERTIGO'
        ctc.distance_start=self.distance_start; ctc.distance_end=self.distance_end
        ctc.height_start=self.height_start; ctc.height_end=self.height_end
        ctc.base_distance=self.base_distance; ctc.base_lens=self.base_lens
        ctc.magnitude=self.magnitude
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        follow=_add_follow_path(cam,path); _add_track_to(cam,tgt)
        ctc.follow_cname=follow.name
        # Driver precisa do cam object já existente
        _setup_vertigo_driver(cam,tgt)
        if self.create_animation:
            _create_follow_path_animation(cam,follow.name,int(self.frame_start),int(self.frame_end),'LINEAR','EASE_OUT')
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Vertigo)"); return {"FINISHED"}


# ── Operator: Handheld Camera ────────────────────────────────
class OBJECT_OT_add_handheld_camera(Operator):
    bl_idname="object.add_handheld_camera"; bl_label="Handheld Camera"
    bl_description="Câmera handheld: arco parcial com jitter de posição baked + noise de roll e target"
    bl_options={"REGISTER","UNDO"}
    radius:           FloatProperty(name="Raio",            default=0.250,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height:           FloatProperty(name="Altura",          default=0.050,soft_min=-1.0,soft_max=1.0, unit="LENGTH",precision=4)
    arc_angle:        FloatProperty(name="Abertura do Arco",default=0.5236,min=0.0873,max=3.14159,    subtype='ANGLE',unit='ROTATION')
    hh_pos_strength:  FloatProperty(name="Noise de Posição",default=0.0003,min=0.0,soft_max=0.005,    unit='LENGTH',precision=4)
    hh_rot_strength:  FloatProperty(name="Amplitude (roll)",default=0.003, min=0.0,soft_max=math.radians(10), subtype="ANGLE",unit="ROTATION")
    hh_rot_scale:     FloatProperty(name="Período roll (fr)",default=15.0, min=0.5,soft_max=200.0,    precision=1)
    hh_target_strength:FloatProperty(name="Amplitude (target)",default=0.0001,min=0.0,soft_max=0.002,unit='LENGTH',precision=4)
    hh_noise_scale:   FloatProperty(name="Frequência (path)",  default=12.0, min=0.1,soft_max=100.0, precision=1)
    hh_target_scale:  FloatProperty(name="Frequência (target)",default=8.0,  min=0.1,soft_max=100.0, precision=1)
    hh_phase:         FloatProperty(name="Phase (Seed)",       default=0.0,  precision=2)
    create_animation: BoolProperty(name="Create Animation", default=True)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof_loc=cur+Vector((0,self.radius*0.6,self.height))
        dof=_new_dof(n,pr,dof_loc,coll)
        path=_make_handheld_path(
            f"Path_TCamera_{n}",self.radius,self.height,self.arc_angle,
            self.hh_pos_strength,self.hh_noise_scale,self.hh_phase,cur,
            resolution=pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='HANDHELD'
        ctc.radius=self.radius; ctc.height=self.height; ctc.arc_angle=self.arc_angle
        ctc.hh_pos_strength=self.hh_pos_strength
        ctc.hh_target_strength=self.hh_target_strength
        ctc.hh_noise_scale=self.hh_noise_scale; ctc.hh_target_scale=self.hh_target_scale
        ctc.hh_phase=self.hh_phase
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=cur; coll.objects.link(cam)
        # Follow Path + Track To diretamente na câmera
        fp=_add_follow_path(cam,path)
        tt=cam.constraints.new("TRACK_TO")
        tt.target=tgt; tt.track_axis="TRACK_NEGATIVE_Z"; tt.up_axis="UP_Y"
        ctc.follow_cname=fp.name
        ease_s=ctc.ease_start; ease_e=ctc.ease_end
        if self.create_animation:
            _create_follow_path_animation(cam,fp.name,int(self.frame_start),int(self.frame_end),ease_s,ease_e)
        _apply_handheld_noise(cam,tgt,self.hh_target_strength,
                              self.hh_target_scale,self.hh_phase,
                              int(self.frame_start),int(self.frame_end))
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Handheld)"); return {"FINISHED"}


class OBJECT_OT_ctc_update_handheld(Operator):
    bl_idname="object.ctc_update_handheld"; bl_label="Atualizar Handheld"
    bl_description="Reconstrói o path e atualiza os noise modifiers com os parâmetros atuais"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        obj=context.active_object
        if not obj or obj.type!='CAMERA':
            self.report({"ERROR"},"Selecione uma TCamera primeiro."); return {"CANCELLED"}
        ctc=obj.data.ctc
        if ctc.rig_type!='HANDHELD':
            self.report({"ERROR"},"Rig não é Handheld."); return {"CANCELLED"}
        p=bpy.data.objects.get(ctc.path_name)
        tgt=bpy.data.objects.get(ctc.target_name)
        if p:
            sp=p.data.splines[0]; n=len(sp.points)
            import mathutils
            for i in range(n):
                t=i/(n-1); angle=-ctc.arc_angle/2+t*ctc.arc_angle
                xb=ctc.radius*math.sin(angle); yb=ctc.radius*math.cos(angle); zb=ctc.height
                nv=mathutils.Vector((xb*ctc.hh_noise_scale+ctc.hh_phase,
                                     yb*ctc.hh_noise_scale+ctc.hh_phase, i*0.07))
                nx=mathutils.noise.noise(nv+mathutils.Vector((0,0,0)))*ctc.hh_pos_strength
                ny=mathutils.noise.noise(nv+mathutils.Vector((100,0,0)))*ctc.hh_pos_strength
                nz=mathutils.noise.noise(nv+mathutils.Vector((0,100,0)))*ctc.hh_pos_strength*0.35
                sp.points[i].co=(xb+nx, yb+ny, zb+nz, 1.0)
            p.data.update_tag()
        _remove_handheld_noise(tgt)
        _apply_handheld_noise(obj, tgt, ctc.hh_target_strength,
                              ctc.hh_target_scale, ctc.hh_phase,
                              ctc.frame_start, ctc.frame_end)
        if ctc.has_animation:
            _create_follow_path_animation(obj,ctc.follow_cname,ctc.frame_start,ctc.frame_end,
                                          ctc.ease_start,ctc.ease_end)
        context.view_layer.update(); return {"FINISHED"}


# ── Operator: Handheld Direct Camera ─────────────────────────
class OBJECT_OT_add_handheld_direct_camera(Operator):
    bl_idname="object.add_handheld_direct_camera"; bl_label="Handheld Camera (Direto)"
    bl_description=(
        "Câmera handheld sem empty intermediário: Follow Path com Follow Curve "
        "+ Damped Track diretamente na câmera. Roll via FCurve Noise."
    )
    bl_options={"REGISTER","UNDO"}
    radius:           FloatProperty(name="Raio",            default=0.250,min=0.0001,soft_max=1000.0,unit="LENGTH",precision=4)
    height:           FloatProperty(name="Altura",          default=0.050,soft_min=-1.0,soft_max=1.0, unit="LENGTH",precision=4)
    arc_angle:        FloatProperty(name="Ângulo do Arco",  default=0.5236,min=0.0873,max=3.14159,    subtype='ANGLE',unit='ROTATION')
    hh_pos_strength:  FloatProperty(name="Amplitude (path)",default=0.0003,min=0.0,soft_max=0.005,    unit='LENGTH',precision=4)
    hh_rot_strength:  FloatProperty(name="Amplitude (roll)",default=0.003, min=0.0,soft_max=math.radians(10),subtype="ANGLE",unit="ROTATION")
    hh_rot_scale:     FloatProperty(name="Período roll (fr)",default=15.0, min=0.5,soft_max=200.0,    precision=1)
    hh_target_strength:FloatProperty(name="Amplitude (target)",default=0.0001,min=0.0,soft_max=0.002,unit='LENGTH',precision=4)
    hh_noise_scale:   FloatProperty(name="Escala espacial (path)",default=12.0,min=0.1,soft_max=100.0,precision=1)
    hh_target_scale:  FloatProperty(name="Período (target fr)",default=8.0,min=0.5,soft_max=200.0,   precision=1)
    hh_phase:         FloatProperty(name="Phase (Seed)",    default=0.0,   precision=2)
    create_animation: BoolProperty(name="Criar Animação",   default=True)
    frame_start: FloatProperty(name="Frame Start",default=0.0,  precision=0)
    frame_end:   FloatProperty(name="Frame End",  default=250.0,precision=0)

    def execute(self, context):
        addon=context.preferences.addons.get(ADDON_ID)
        if not addon: return {"CANCELLED"}
        pr=addon.preferences; n=_next_camera_number()
        cur=Vector(context.scene.cursor.location)
        coll=_prepare_collection(n,pr,context)
        tgt=_new_target(n,pr,cur,coll)
        dof_loc=cur+Vector((0,self.radius*0.6,self.height))
        dof=_new_dof(n,pr,dof_loc,coll)
        path=_make_handheld_path(
            f"Path_TCamera_{n}",self.radius,self.height,self.arc_angle,
            self.hh_pos_strength,self.hh_noise_scale,self.hh_phase,cur,
            resolution=pr.spline_resolution)
        coll.objects.link(path)
        cam_data=_new_camera(n,pr); cam_data.dof.use_dof=True; cam_data.dof.focus_object=dof
        ctc=cam_data.ctc; ctc.rig_type='HANDHELD_DIRECT'
        ctc.radius=self.radius; ctc.height=self.height; ctc.arc_angle=self.arc_angle
        ctc.hh_pos_strength=self.hh_pos_strength
        ctc.hh_rot_strength=self.hh_rot_strength; ctc.hh_rot_scale=self.hh_rot_scale
        ctc.hh_target_strength=self.hh_target_strength
        ctc.hh_noise_scale=self.hh_noise_scale; ctc.hh_target_scale=self.hh_target_scale
        ctc.hh_phase=self.hh_phase
        ctc.target_name=tgt.name; ctc.dof_name=dof.name; ctc.path_name=path.name
        ctc.frame_start=int(self.frame_start); ctc.frame_end=int(self.frame_end)
        ctc.has_animation=self.create_animation
        cam=bpy.data.objects.new(f"TCamera_{n}",cam_data)
        cam.location=Vector((0,0,0)); coll.objects.link(cam)
        # Follow Path com Follow Curve + Damped Track direto na câmera
        fp=cam.constraints.new("FOLLOW_PATH")
        fp.target=path; fp.use_fixed_location=False; fp.use_curve_follow=False
        lt=cam.constraints.new("LOCKED_TRACK")
        lt.target=tgt; lt.track_axis="TRACK_NEGATIVE_Z"; lt.lock_axis="LOCK_Y"
        ctc.follow_cname=fp.name
        if self.create_animation:
            _create_follow_path_animation(cam,fp.name,int(self.frame_start),int(self.frame_end),
                                          ctc.ease_start,ctc.ease_end)
        # Roll noise direto na câmera
        if cam.animation_data is None: cam.animation_data_create()
        cam.keyframe_insert(data_path="rotation_euler", index=2, frame=int(self.frame_start))
        cam.keyframe_insert(data_path="rotation_euler", index=2, frame=int(self.frame_end))
        for fc in _iter_action_fcurves(cam):
            if fc.data_path=="rotation_euler" and fc.array_index==2:
                mod=fc.modifiers.new('NOISE')
                mod.scale=self.hh_rot_scale; mod.strength=self.hh_rot_strength
                mod.phase=self.hh_phase
                break
        # Target delta_location noise
        _apply_handheld_noise.__func__ if hasattr(_apply_handheld_noise,'__func__') else None
        tgt.delta_location=(0,0,0)
        if tgt.animation_data is None: tgt.animation_data_create()
        for i in range(3):
            tgt.keyframe_insert(data_path="delta_location", index=i, frame=int(self.frame_start))
            tgt.keyframe_insert(data_path="delta_location", index=i, frame=int(self.frame_end))
        phase_offsets=(7.3,13.7,21.1); z_scale=0.45
        for fc in _iter_action_fcurves(tgt):
            if fc.data_path=="delta_location" and fc.array_index in (0,1,2):
                idx=fc.array_index
                mod=fc.modifiers.new('NOISE')
                mod.scale=self.hh_target_scale
                mod.strength=self.hh_target_strength*(z_scale if idx==2 else 1.0)
                mod.phase=self.hh_phase+phase_offsets[idx]
        for o in context.selected_objects: o.select_set(False)
        cam.select_set(True); context.view_layer.objects.active=cam
        self.report({"INFO"},f"Created TCamera_{n} (Handheld Direct)"); return {"FINISHED"}


class OBJECT_OT_ctc_update_handheld_direct(Operator):
    bl_idname="object.ctc_update_handheld_direct"; bl_label="Atualizar Handheld Direct"
    bl_description="Reconstrói path e reaplica noise de roll e target"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        obj=context.active_object
        if not obj or obj.type!='CAMERA':
            self.report({"ERROR"},"Selecione uma TCamera primeiro."); return {"CANCELLED"}
        ctc=obj.data.ctc
        if ctc.rig_type!='HANDHELD_DIRECT':
            self.report({"ERROR"},"Rig não é Handheld Direct."); return {"CANCELLED"}
        p=bpy.data.objects.get(ctc.path_name)
        tgt=bpy.data.objects.get(ctc.target_name)
        if p:
            import mathutils
            sp=p.data.splines[0]; n=len(sp.points)
            for i in range(n):
                t=i/(n-1); angle=-ctc.arc_angle/2+t*ctc.arc_angle
                xb=ctc.radius*math.sin(angle); yb=ctc.radius*math.cos(angle); zb=ctc.height
                nv=mathutils.Vector((xb*ctc.hh_noise_scale+ctc.hh_phase,
                                     yb*ctc.hh_noise_scale+ctc.hh_phase,i*0.07))
                nx=mathutils.noise.noise(nv+mathutils.Vector((0,0,0)))*ctc.hh_pos_strength
                ny=mathutils.noise.noise(nv+mathutils.Vector((100,0,0)))*ctc.hh_pos_strength
                nz=mathutils.noise.noise(nv+mathutils.Vector((0,100,0)))*ctc.hh_pos_strength*0.35
                sp.points[i].co=(xb+nx,yb+ny,zb+nz,1.0)
            p.data.update_tag()
        # Remove e reaplica noise de roll
        for fc in _iter_action_fcurves(obj):
            if fc.data_path=="rotation_euler" and fc.array_index==2:
                for m in list(fc.modifiers):
                    if m.type=='NOISE': fc.modifiers.remove(m)
                mod=fc.modifiers.new('NOISE')
                mod.scale=ctc.hh_rot_scale; mod.strength=ctc.hh_rot_strength
                mod.phase=ctc.hh_phase
        # Remove e reaplica noise de target
        if tgt:
            for fc in _iter_action_fcurves(tgt):
                if fc.data_path=="delta_location":
                    for m in list(fc.modifiers):
                        if m.type=='NOISE': fc.modifiers.remove(m)
            phase_offsets=(7.3,13.7,21.1); z_scale=0.45
            for fc in _iter_action_fcurves(tgt):
                if fc.data_path=="delta_location" and fc.array_index in (0,1,2):
                    idx=fc.array_index
                    mod=fc.modifiers.new('NOISE')
                    mod.scale=ctc.hh_target_scale
                    mod.strength=ctc.hh_target_strength*(z_scale if idx==2 else 1.0)
                    mod.phase=ctc.hh_phase+phase_offsets[idx]
        # Recriar animação do Follow Path
        if ctc.has_animation:
            _create_follow_path_animation(obj,ctc.follow_cname,ctc.frame_start,ctc.frame_end,
                                          ctc.ease_start,ctc.ease_end)
        context.view_layer.update(); return {"FINISHED"}


# ── Operator: Update Path ─────────────────────────────────────

class OBJECT_OT_ctc_update_path(Operator):
    bl_idname="object.ctc_update_path"; bl_label="Aplicar Alterações no Path"
    bl_description="Reconstrói o(s) path(s) do rig com os parâmetros atuais"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        obj=context.active_object
        if not obj or obj.type!='CAMERA':
            self.report({"ERROR"},"Selecione uma TCamera primeiro."); return {"CANCELLED"}
        ctc=obj.data.ctc
        p=bpy.data.objects.get(ctc.path_name)
        if ctc.rig_type in ('CIRCLE','DUAL_CIRCLE'):
            if p: _rebuild_circle_spline(p,ctc.radius)
            dp=bpy.data.objects.get(ctc.dof_path_name)
            if ctc.rig_type=='DUAL_CIRCLE' and dp:
                _rebuild_circle_spline(dp,ctc.dof_radius)
        elif ctc.rig_type in ('HELIX','DUAL_HELIX'):
            if p: _rebuild_helix_spline(p,ctc.radius,ctc.radius_end,ctc.height)
            dp=bpy.data.objects.get(ctc.dof_path_name)
            if ctc.rig_type=='DUAL_HELIX' and dp:
                _rebuild_helix_spline(dp,ctc.dof_radius,ctc.dof_radius_end,ctc.height)
        elif ctc.rig_type in ('DOLLY','VERTIGO'):
            if p: _rebuild_dolly_spline(p,ctc.distance_start,ctc.distance_end,ctc.height_start,ctc.height_end)
        elif ctc.rig_type=='CRANE':
            if p: _rebuild_crane_spline(p,ctc.radius,ctc.height_start,ctc.height_end,
                                        ctc.azimuth_start,ctc.azimuth_end)
        context.view_layer.update(); return {"FINISHED"}


# ── Operator: Update Animation ────────────────────────────────

class OBJECT_OT_ctc_update_animation(Operator):
    bl_idname="object.ctc_update_animation"; bl_label="Aplicar Animação"
    bl_description="Cria ou reconstrói os keyframes de Follow Path com easing"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        obj=context.active_object
        if not obj or obj.type!='CAMERA':
            self.report({"ERROR"},"Selecione uma TCamera primeiro."); return {"CANCELLED"}
        ctc=obj.data.ctc
        if ctc.rig_type=='STATIC':
            self.report({"WARNING"},"Câmeras estáticas não têm Follow Path."); return {"CANCELLED"}
        anim_obj = obj
        cn=ctc.follow_cname
        if not cn or cn not in anim_obj.constraints:
            for c in anim_obj.constraints:
                if c.type=='FOLLOW_PATH': cn=c.name; ctc.follow_cname=cn; break
        if not cn:
            self.report({"ERROR"},"Follow Path constraint não encontrado."); return {"CANCELLED"}
        _create_follow_path_animation(anim_obj,cn,ctc.frame_start,ctc.frame_end,ctc.ease_start,ctc.ease_end)
        ctc.has_animation=True
        if ctc.rig_type in ('DUAL_CIRCLE','DUAL_HELIX'):
            do=bpy.data.objects.get(ctc.dof_name); dc=ctc.dof_follow_cname
            if do and dc and dc in do.constraints:
                _create_follow_path_animation(do,dc,ctc.frame_start,ctc.frame_end,ctc.ease_start,ctc.ease_end)
        return {"FINISHED"}


# ── Operator: Update Vertigo Driver ──────────────────────────

class OBJECT_OT_ctc_update_vertigo_driver(Operator):
    bl_idname="object.ctc_update_vertigo_driver"; bl_label="Atualizar Driver Vertigo"
    bl_description="Reconstrói o driver de lente com os parâmetros atuais do painel"
    bl_options={"REGISTER","UNDO"}

    def execute(self, context):
        obj=context.active_object
        if not obj or obj.type!='CAMERA':
            self.report({"ERROR"},"Selecione uma TCamera Vertigo primeiro."); return {"CANCELLED"}
        ctc=obj.data.ctc
        if ctc.rig_type!='VERTIGO':
            self.report({"ERROR"},"Este operador é exclusivo de câmeras Vertigo."); return {"CANCELLED"}
        tgt=bpy.data.objects.get(ctc.target_name)
        if not tgt:
            self.report({"ERROR"},f"Target '{ctc.target_name}' não encontrado."); return {"CANCELLED"}
        obj.data.lens=ctc.base_lens
        _setup_vertigo_driver(obj,tgt)
        self.report({"INFO"},"Driver Vertigo atualizado."); return {"FINISHED"}


# ── N-panel ───────────────────────────────────────────────────

_RIG_LABELS = {
    'STATIC':'Static','CIRCLE':'Orbit','DUAL_CIRCLE':'Dual Orbit',
    'HELIX':'Helix','DUAL_HELIX':'Dual Helix',
    'DOLLY':'Dolly','CRANE':'Crane','VERTIGO':'Vertigo','HANDHELD':'Handheld',
}

class VIEW3D_PT_ctc_rig(Panel):
    bl_label="TCamera Rig"; bl_space_type="VIEW_3D"
    bl_region_type="UI"; bl_category="TCamera"

    @classmethod
    def poll(cls,context):
        o=context.active_object
        return (o and o.type=='CAMERA' and hasattr(o.data,'ctc')
                and o.data.ctc.rig_type!='NONE')

    def draw(self,context):
        obj=context.active_object; ctc=obj.data.ctc; layout=self.layout
        rt=ctc.rig_type

        # Cabeçalho
        box=layout.box()
        box.label(text=f"{obj.name}  ·  {_RIG_LABELS.get(rt,rt)}",icon="CAMERA_DATA")

        # ── Path (orbit / helix) ──────────────────────────────
        if rt in ('CIRCLE','DUAL_CIRCLE','HELIX','DUAL_HELIX'):
            box=layout.box(); box.label(text="Path",icon="CURVE_BEZCIRCLE")
            col=box.column(align=True)
            if rt in ('CIRCLE','DUAL_CIRCLE'):
                col.prop(ctc,"radius",text="Câmera — Raio")
                if rt=='DUAL_CIRCLE': col.prop(ctc,"dof_radius",text="DoF — Raio")
            else:
                col.prop(ctc,"radius",    text="Câmera — Raio inicial")
                col.prop(ctc,"radius_end",text="Câmera — Raio final")
                col.prop(ctc,"height",    text="Altura")
                if rt=='DUAL_HELIX':
                    col.separator()
                    col.prop(ctc,"dof_radius",    text="DoF — Raio inicial")
                    col.prop(ctc,"dof_radius_end",text="DoF — Raio final")
            box.operator("object.ctc_update_path",icon="FILE_REFRESH")

        # ── Path (dolly / vertigo) ────────────────────────────
        if rt in ('DOLLY','VERTIGO'):
            box=layout.box(); box.label(text="Path",icon="CURVE_BEZCIRCLE")
            col=box.column(align=True)
            col.prop(ctc,"distance_start",text="Distância inicial")
            col.prop(ctc,"distance_end",  text="Distância final")
            col.separator()
            col.prop(ctc,"height_start",text="Altura inicial")
            col.prop(ctc,"height_end",  text="Altura final")
            box.operator("object.ctc_update_path",icon="FILE_REFRESH")

        # ── Path (crane) ──────────────────────────────────────
        if rt=='CRANE':
            box=layout.box(); box.label(text="Path",icon="CURVE_BEZCIRCLE")
            col=box.column(align=True)
            col.prop(ctc,"radius",       text="Raio horizontal")
            col.separator()
            col.prop(ctc,"height_start", text="Altura inicial")
            col.prop(ctc,"height_end",   text="Altura final")
            col.separator()
            col.prop(ctc,"azimuth_start",text="Azimute inicial")
            col.prop(ctc,"azimuth_end",  text="Azimute final")
            box.operator("object.ctc_update_path",icon="FILE_REFRESH")

        # ── Handheld ─────────────────────────────────────────
        if rt=='HANDHELD':
            box=layout.box(); box.label(text="Path",icon="CURVE_BEZCIRCLE")
            col=box.column(align=True)
            col.prop(ctc,"radius",   text="Distância do centro")
            col.prop(ctc,"height",   text="Altura")
            col.prop(ctc,"arc_angle",text="Ângulo do arco")
            box=layout.box(); box.label(text="Noise — Path (posição, baked)",icon="MOD_NOISE")
            col=box.column(align=True)
            col.prop(ctc,"hh_pos_strength",text="Amplitude")
            col.prop(ctc,"hh_noise_scale", text="Escala espacial")
            box=layout.box(); box.label(text="Noise — Target (pan/tilt)",icon="EMPTY_AXIS")
            col=box.column(align=True)
            col.prop(ctc,"hh_target_strength",text="Amplitude")
            col.prop(ctc,"hh_target_scale",   text="Período (frames)")
            box=layout.box(); box.label(text="Noise — Roll da câmera",icon="ORIENTATION_GIMBAL")
            col=box.column(align=True)
            col.prop(ctc,"hh_rot_strength",text="Amplitude (rad)")
            col.prop(ctc,"hh_rot_scale",   text="Período (frames)")
            col.separator()
            col=layout.column(align=True)
            col.prop(ctc,"hh_phase",text="Phase / Seed")
            layout.operator("object.ctc_update_handheld",icon="FILE_REFRESH")

        # ── Vertigo driver ────────────────────────────────────
        if rt=='VERTIGO':
            box=layout.box(); box.label(text="Efeito Vertigo",icon="DRIVER")
            col=box.column(align=True)
            col.prop(ctc,"base_distance",text="Distância de base")
            col.prop(ctc,"base_lens",    text="Focal de base (mm)")
            col.prop(ctc,"magnitude",    text="Magnitude")
            box.operator("object.ctc_update_vertigo_driver",icon="FILE_REFRESH")

        # ── Animação ─────────────────────────────────────────
        if rt!='STATIC':
            box=layout.box(); box.label(text="Animação",icon="ANIM")
            col=box.column(align=True)
            col.prop(ctc,"frame_start",text="Frame início")
            col.prop(ctc,"frame_end",  text="Frame fim")
            col.separator()
            sub=col.column(align=True); sub.label(text="Suavização:")
            row=sub.row(align=True)
            row.prop(ctc,"ease_start",text="Início"); row.prop(ctc,"ease_end",text="Final")
            lbl="Atualizar Animação" if ctc.has_animation else "Criar Animação"
            ico="FILE_REFRESH"       if ctc.has_animation else "ANIM_DATA"
            box.operator("object.ctc_update_animation",text=lbl,icon=ico)

        # ── Objetos do rig ────────────────────────────────────
        box=layout.box(); box.label(text="Objetos do rig",icon="OUTLINER_OB_EMPTY")
        col=box.column(align=True)
        if ctc.target_name:       col.label(text=f"Target:      {ctc.target_name}",      icon="EMPTY_AXIS")
        if ctc.dof_name:          col.label(text=f"DoF:         {ctc.dof_name}",          icon="EMPTY_AXIS")
        if ctc.follow_empty_name: col.label(text=f"Follow Empty:{ctc.follow_empty_name}",  icon="EMPTY_PLAIN_AXES")
        if ctc.path_name:         col.label(text=f"Path:        {ctc.path_name}",          icon="CURVE_BEZCIRCLE")
        if ctc.dof_path_name:     col.label(text=f"DoF Path:    {ctc.dof_path_name}",      icon="CURVE_BEZCIRCLE")


# ── Menu ──────────────────────────────────────────────────────

def _menu_func(self,context):
    layout=self.layout; layout.separator()
    layout.operator("object.add_tracked_camera",       text="Static Camera",          icon="CAMERA_DATA")
    layout.operator("object.add_tracked_path_camera",  text="Orbit Camera",           icon="CAMERA_DATA")
    layout.operator("object.add_tracked_dual_path_camera",text="Orbit Camera + DoF Orbit",icon="CAMERA_DATA")
    layout.operator("object.add_tracked_spiral_camera",text="Helix Camera",           icon="CAMERA_DATA")
    layout.operator("object.add_tracked_dual_spiral_camera",text="Helix Camera + DoF Helix",icon="CAMERA_DATA")
    layout.separator()
    layout.operator("object.add_dolly_camera",         text="Dolly Camera",           icon="CAMERA_DATA")
    layout.operator("object.add_crane_camera",         text="Crane Camera",           icon="CAMERA_DATA")
    layout.operator("object.add_vertigo_camera",       text="Vertigo Camera",         icon="CAMERA_DATA")
    layout.operator("object.add_handheld_camera",       text="Handheld Camera",        icon="CAMERA_DATA")


# ── Registration ──────────────────────────────────────────────

_classes = (
    CreateTrackedCamerasPreferences,
    PREFERENCES_OT_ctc_save_ini,
    PREFERENCES_OT_ctc_load_ini,
    OBJECT_OT_add_tracked_camera,
    OBJECT_OT_add_tracked_path_camera,
    OBJECT_OT_add_tracked_dual_path_camera,
    OBJECT_OT_add_tracked_spiral_camera,
    OBJECT_OT_add_tracked_dual_spiral_camera,
    OBJECT_OT_add_dolly_camera,
    OBJECT_OT_add_crane_camera,
    OBJECT_OT_add_vertigo_camera,
    OBJECT_OT_add_handheld_camera,
    OBJECT_OT_ctc_update_handheld,
    OBJECT_OT_ctc_update_path,
    OBJECT_OT_ctc_update_animation,
    OBJECT_OT_ctc_update_vertigo_driver,
    VIEW3D_PT_ctc_rig,
)

def _load_prefs_from_ini_delayed():
    try:
        addon=bpy.context.preferences.addons.get(ADDON_ID)
        if not addon: return None
        v=load_ini_values(); p=addon.preferences
        p.target_empty_size=v["target_empty_size"]; p.camera_display_size=v["camera_display_size"]
        p.dof_empty_size=v["dof_empty_size"]; p.camera_distance=v["camera_distance"]
        p.clip_start=v["clip_start"]; p.clip_end=v["clip_end"]
        p.use_collection=v["use_collection"]; p.circle_radius=v["circle_radius"]
        p.target_circle_radius=v["target_circle_radius"]; p.spline_resolution=v["spline_resolution"]
        p.dof_fstop=v["dof_fstop"]; p.dof_blades=v["dof_blades"]
        p.dof_rotation=v["dof_rotation"]; p.dof_ratio=v["dof_ratio"]
    except Exception as e:
        print(f"[CreateTrackedCameras] Could not load INI on startup: {e}")
    return None

def register():
    bpy.utils.register_class(CTCRigProperties)
    bpy.types.Camera.ctc=PointerProperty(type=CTCRigProperties)
    for cls in _classes: bpy.utils.register_class(cls)
    mc=getattr(bpy.types,"VIEW3D_MT_camera_add",None) or bpy.types.VIEW3D_MT_add
    old=bpy.app.driver_namespace.pop("_ctc_menu_func",None)
    if old is not None:
        try: mc.remove(old)
        except: pass
    mc.append(_menu_func)
    bpy.app.driver_namespace["_ctc_menu_func"]=_menu_func
    bpy.app.timers.register(_load_prefs_from_ini_delayed,first_interval=0.5)

def unregister():
    mc=getattr(bpy.types,"VIEW3D_MT_camera_add",None) or bpy.types.VIEW3D_MT_add
    old=bpy.app.driver_namespace.pop("_ctc_menu_func",None)
    try: mc.remove(old or _menu_func)
    except: pass
    for cls in reversed(_classes): bpy.utils.unregister_class(cls)
    del bpy.types.Camera.ctc
    bpy.utils.unregister_class(CTCRigProperties)

if __name__=="__main__": register()
