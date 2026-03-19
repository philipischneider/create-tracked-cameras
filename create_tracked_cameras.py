# ==============================================================
# Create Tracked Cameras - Blender Add-on
# Compatible: Blender 5.0+
# ==============================================================
#
# Installation:
#   Edit > Preferences > Add-ons > Install from File...
#   Select this file and enable the add-on.
#
# Usage:
#   Shift+A > Tracked Camera
#   Shift+A > Tracked Camera + Follow Path
#
# Settings:
#   Edit > Preferences > Add-ons > Create Tracked Cameras
#   Config file: %USERPROFILE%\create_tracked_cameras.ini
# ==============================================================

bl_info = {
    "name": "Create Tracked Cameras",
    "author": "philipischneider",
    "version": (1, 1, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Shift+A > Tracked Camera",
    "description": (
        "Creates cameras pre-configured with Track To, optional Follow Path, "
        "target empty, and Depth of Field focus empty"
    ),
    "warning": "",
    "doc_url": "https://github.com/philipischneider/create-tracked-cameras",
    "category": "Camera",
}

import re
import math
import configparser

import bpy
from bpy.props import BoolProperty, FloatProperty
from bpy.types import AddonPreferences, Operator
from mathutils import Vector
from pathlib import Path


# ── Constants ─────────────────────────────────────────────────

ADDON_ID     = "create_tracked_cameras"
INI_FILENAME = "create_tracked_cameras.ini"

_DEFAULTS = {
    # Display / placement
    "target_empty_size":   0.010,   # 10 mm
    "camera_display_size": 0.025,   # 25 mm
    "dof_empty_size":      0.010,   # 10 mm
    "camera_distance":     0.050,   # 50 mm  (simple tracked camera)
    # Collection
    "use_collection":      False,
    # Follow Path
    "circle_radius":       0.250,   # 250 mm
}

# Float keys that are read/written as floats in the INI
_FLOAT_KEYS = (
    "target_empty_size",
    "camera_display_size",
    "dof_empty_size",
    "camera_distance",
    "circle_radius",
)

# Boolean keys in the INI
_BOOL_KEYS = (
    "use_collection",
)


# ── INI helpers ───────────────────────────────────────────────

def get_ini_path() -> Path:
    """Returns the path to the INI file in the user's home directory."""
    return Path.home() / INI_FILENAME


def load_ini_values() -> dict:
    """
    Read values from the INI file.
    Keys that are missing or malformed fall back to _DEFAULTS.
    """
    result = dict(_DEFAULTS)
    ini_path = get_ini_path()

    if not ini_path.exists():
        return result

    config = configparser.ConfigParser()
    config.read(ini_path, encoding="utf-8")

    if "Settings" not in config:
        return result

    for key in _FLOAT_KEYS:
        try:
            result[key] = float(config["Settings"][key])
        except (KeyError, ValueError):
            pass

    for key in _BOOL_KEYS:
        try:
            result[key] = config.getboolean("Settings", key,
                                            fallback=_DEFAULTS[key])
        except (ValueError, TypeError):
            pass

    return result


def save_ini_values(values: dict) -> None:
    """Write a values dict to the INI file, creating it if needed."""
    config = configparser.ConfigParser()
    settings = {}
    for key in _FLOAT_KEYS:
        settings[key] = f"{values[key]:.6f}"
    for key in _BOOL_KEYS:
        settings[key] = "1" if values[key] else "0"
    config["Settings"] = settings
    with open(get_ini_path(), "w", encoding="utf-8") as f:
        config.write(f)


# ── Preferences ───────────────────────────────────────────────

class CreateTrackedCamerasPreferences(AddonPreferences):
    bl_idname = ADDON_ID

    # ── Sizes & distances ──────────────────────────────────────

    target_empty_size: FloatProperty(
        name="Target Empty Size",
        description="Viewport display size of the Track To target empty",
        default=_DEFAULTS["target_empty_size"],
        min=0.0001,
        soft_max=10.0,
        unit="LENGTH",
        precision=4,
    )
    camera_display_size: FloatProperty(
        name="Camera Display Size",
        description="Viewport display size of the camera frustum",
        default=_DEFAULTS["camera_display_size"],
        min=0.0001,
        soft_max=10.0,
        unit="LENGTH",
        precision=4,
    )
    dof_empty_size: FloatProperty(
        name="DoF Empty Size",
        description="Viewport display size of the Depth of Field focus empty",
        default=_DEFAULTS["dof_empty_size"],
        min=0.0001,
        soft_max=10.0,
        unit="LENGTH",
        precision=4,
    )
    camera_distance: FloatProperty(
        name="Camera Distance",
        description=(
            "Default horizontal distance between camera and target empty "
            "(Tracked Camera only)"
        ),
        default=_DEFAULTS["camera_distance"],
        min=0.0001,
        soft_max=1000.0,
        unit="LENGTH",
        precision=4,
    )

    # ── Collection ─────────────────────────────────────────────

    use_collection: BoolProperty(
        name="Create Collection per Camera",
        description=(
            "Group each camera and its associated objects inside a new "
            "collection named after the camera"
        ),
        default=_DEFAULTS["use_collection"],
    )

    # ── Follow Path ────────────────────────────────────────────

    circle_radius: FloatProperty(
        name="Circle Radius",
        description="Radius of the Bezier circle path for Tracked Camera + Follow Path",
        default=_DEFAULTS["circle_radius"],
        min=0.0001,
        soft_max=1000.0,
        unit="LENGTH",
        precision=4,
    )

    # ── Draw ───────────────────────────────────────────────────

    def draw(self, context):
        layout = self.layout

        # INI file path
        box = layout.box()
        split = box.split(factor=0.2)
        split.label(text="Config file:", icon="FILE_TEXT")
        split.label(text=str(get_ini_path()))

        layout.separator()

        # Sizes & distances
        box = layout.box()
        box.label(text="Sizes and distances:", icon="OBJECT_DATA")
        col = box.column(align=True)
        col.prop(self, "target_empty_size")
        col.prop(self, "dof_empty_size")
        col.prop(self, "camera_display_size")
        col.prop(self, "camera_distance")

        layout.separator()

        # Collection
        box = layout.box()
        box.label(text="Organisation:", icon="OUTLINER_COLLECTION")
        box.prop(self, "use_collection")

        layout.separator()

        # Follow Path
        box = layout.box()
        box.label(text="Tracked Camera + Follow Path:", icon="CURVE_BEZCIRCLE")
        box.prop(self, "circle_radius")

        layout.separator()

        row = layout.row(align=True)
        row.operator("preferences.ctc_save_ini", icon="EXPORT")
        row.operator("preferences.ctc_load_ini", icon="IMPORT")


# ── Preferences operators ─────────────────────────────────────

class PREFERENCES_OT_ctc_save_ini(Operator):
    bl_idname = "preferences.ctc_save_ini"
    bl_label = "Save to INI"
    bl_description = "Write the current preference values to the INI config file"

    def execute(self, context):
        prefs = context.preferences.addons[ADDON_ID].preferences
        save_ini_values({
            "target_empty_size":   prefs.target_empty_size,
            "camera_display_size": prefs.camera_display_size,
            "dof_empty_size":      prefs.dof_empty_size,
            "camera_distance":     prefs.camera_distance,
            "use_collection":      prefs.use_collection,
            "circle_radius":       prefs.circle_radius,
        })
        self.report({"INFO"}, f"Saved → {get_ini_path()}")
        return {"FINISHED"}


class PREFERENCES_OT_ctc_load_ini(Operator):
    bl_idname = "preferences.ctc_load_ini"
    bl_label = "Load from INI"
    bl_description = "Read preference values from the INI config file"

    def execute(self, context):
        values = load_ini_values()
        prefs  = context.preferences.addons[ADDON_ID].preferences
        prefs.target_empty_size   = values["target_empty_size"]
        prefs.camera_display_size = values["camera_display_size"]
        prefs.dof_empty_size      = values["dof_empty_size"]
        prefs.camera_distance     = values["camera_distance"]
        prefs.use_collection      = values["use_collection"]
        prefs.circle_radius       = values["circle_radius"]
        self.report({"INFO"}, f"Loaded ← {get_ini_path()}")
        return {"FINISHED"}


# ── Shared helpers ────────────────────────────────────────────

def _next_camera_number() -> int:
    """Return the lowest N ≥ 1 not yet used by any TCamera_N object."""
    used = set()
    pattern = re.compile(r"^TCamera_(\d+)$")
    for obj in bpy.data.objects:
        m = pattern.match(obj.name)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return n


def _prepare_collection(n: int, prefs, context) -> bpy.types.Collection:
    """
    Return the collection that new objects should be linked to.

    If prefs.use_collection is True, create a new collection named
    TCamera_<n> under the scene root and return it.
    Otherwise return the currently active collection.
    """
    if prefs.use_collection:
        coll = bpy.data.collections.new(f"TCamera_{n}")
        context.scene.collection.children.link(coll)
        return coll
    return context.collection


def _make_bezier_circle(name: str, radius: float, location: Vector) -> bpy.types.Object:
    """
    Build a closed Bezier circle curve object without using bpy.ops.

    The circle lies in the XY plane (Z = 0) and is centred at *location*.
    The handle length that produces a perfect circle is:
        h = radius * (4/3) * tan(π/8)  ≈  0.5523 * radius
    """
    h = radius * (4.0 / 3.0) * math.tan(math.pi / 8.0)

    # Four control points at East, North, West, South.
    # Each tuple: handle_left, handle_right)
    # CCW traversal: right_handle points in the forward (CCW tangent) direction;
    # left_handle points in the backward direction.
    #
    #  Point  | CCW tangent | handle_left  | handle_right
    #  -------+-------------+--------------+-------------
    #  East   |  (0, +1)    |  (r,  -h)    |  (r,  +h)
    #  North  |  (-1, 0)    |  (+h,  r)    |  (-h,  r)
    #  West   |  (0, -1)    |  (-r, +h)    |  (-r, -h)
    #  South  |  (+1, 0)    |  (-h, -r)    |  (+h, -r)
    point_data = [
        # East  (r, 0)
        (( radius,  0.0,    0.0),
         ( radius, -h,      0.0),   # left  ← backward (toward South)
         ( radius,  h,      0.0)),  # right → forward  (toward North)
        # North (0, r)
        (( 0.0,     radius, 0.0),
         ( h,       radius, 0.0),   # left  ← backward (toward East)
         (-h,       radius, 0.0)),  # right → forward  (toward West)
        # West  (-r, 0)
        ((-radius,  0.0,    0.0),
         (-radius,  h,      0.0),   # left  ← backward (toward North)
         (-radius, -h,      0.0)),  # right → forward  (toward South)
        # South (0, -r)
        (( 0.0,    -radius, 0.0),
         (-h,      -radius, 0.0),   # left  ← backward (toward West)
         ( h,      -radius, 0.0)),  # right → forward  (toward East)
    ]

    curve = bpy.data.curves.new(name, type="CURVE")
    curve.dimensions = "3D"

    spline = curve.splines.new(type="BEZIER")
    spline.bezier_points.add(3)   # new() creates 1 point; add(3) → total 4
    spline.use_cyclic_u = True

    for i, (co, hl, hr) in enumerate(point_data):
        bp = spline.bezier_points[i]
        bp.co                = Vector(co)
        bp.handle_left       = Vector(hl)
        bp.handle_right      = Vector(hr)
        bp.handle_left_type  = "FREE"
        bp.handle_right_type = "FREE"

    obj          = bpy.data.objects.new(name, curve)
    obj.location = location
    return obj


# ── Operator: Tracked Camera ──────────────────────────────────

class OBJECT_OT_add_tracked_camera(Operator):
    bl_idname = "object.add_tracked_camera"
    bl_label = "Tracked Camera"
    bl_description = (
        "Create a camera with a Track To constraint, "
        "a target empty at the 3D cursor, and a Depth of Field focus empty"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon = context.preferences.addons.get(ADDON_ID)
        if addon is None:
            self.report({"ERROR"}, "Add-on preferences not found.")
            return {"CANCELLED"}

        prefs       = addon.preferences
        target_size = prefs.target_empty_size
        cam_size    = prefs.camera_display_size
        dof_size    = prefs.dof_empty_size
        distance    = prefs.camera_distance

        n          = _next_camera_number()
        cursor_loc = Vector(context.scene.cursor.location)
        cam_loc    = cursor_loc + Vector((0.0, distance, 0.0))
        dof_loc    = (cursor_loc + cam_loc) * 0.5

        coll = _prepare_collection(n, prefs, context)

        # Target empty — at 3D cursor
        target_obj = bpy.data.objects.new(f"Target_Camera_{n}", None)
        target_obj.empty_display_type = "PLAIN_AXES"
        target_obj.empty_display_size = target_size
        target_obj.location           = cursor_loc
        coll.objects.link(target_obj)

        # DoF focus empty — midpoint camera ↔ target
        dof_obj = bpy.data.objects.new(f"DoF_Camera_{n}", None)
        dof_obj.empty_display_type = "PLAIN_AXES"
        dof_obj.empty_display_size = dof_size
        dof_obj.location           = dof_loc
        coll.objects.link(dof_obj)

        # Camera
        cam_data              = bpy.data.cameras.new(f"TCamera_{n}")
        cam_data.display_size = cam_size
        cam_data.dof.use_dof      = True
        cam_data.dof.focus_object = dof_obj

        cam_obj          = bpy.data.objects.new(f"TCamera_{n}", cam_data)
        cam_obj.location = cam_loc
        coll.objects.link(cam_obj)

        # Track To constraint
        track            = cam_obj.constraints.new(type="TRACK_TO")
        track.target     = target_obj
        track.track_axis = "TRACK_NEGATIVE_Z"
        track.up_axis    = "UP_Y"

        # Leave camera selected and active
        for obj in context.selected_objects:
            obj.select_set(False)
        cam_obj.select_set(True)
        context.view_layer.objects.active = cam_obj

        self.report(
            {"INFO"},
            f"Created TCamera_{n} → Target_Camera_{n} | DoF: DoF_Camera_{n}",
        )
        return {"FINISHED"}


# ── Operator: Tracked Camera + Follow Path ────────────────────

class OBJECT_OT_add_tracked_path_camera(Operator):
    bl_idname = "object.add_tracked_path_camera"
    bl_label = "Tracked Camera + Follow Path"
    bl_description = (
        "Create a camera that follows a Bezier circle path (Follow Path) "
        "and points at a target empty (Track To), with Depth of Field"
    )
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon = context.preferences.addons.get(ADDON_ID)
        if addon is None:
            self.report({"ERROR"}, "Add-on preferences not found.")
            return {"CANCELLED"}

        prefs       = addon.preferences
        target_size = prefs.target_empty_size
        cam_size    = prefs.camera_display_size
        dof_size    = prefs.dof_empty_size
        radius      = prefs.circle_radius

        n          = _next_camera_number()
        cursor_loc = Vector(context.scene.cursor.location)

        # The path is a circle centred at the cursor.
        # At offset 0 the camera sits at the East point of the circle,
        # i.e. world position ≈ cursor + (radius, 0, 0).
        # The DoF empty is placed at the midpoint between that initial
        # camera position and the target.
        initial_cam_world = cursor_loc + Vector((radius, 0.0, 0.0))
        dof_loc           = (cursor_loc + initial_cam_world) * 0.5

        coll = _prepare_collection(n, prefs, context)

        # Target empty — at 3D cursor (centre of the orbit)
        target_obj = bpy.data.objects.new(f"Target_Camera_{n}", None)
        target_obj.empty_display_type = "PLAIN_AXES"
        target_obj.empty_display_size = target_size
        target_obj.location           = cursor_loc
        coll.objects.link(target_obj)

        # DoF focus empty
        dof_obj = bpy.data.objects.new(f"DoF_Camera_{n}", None)
        dof_obj.empty_display_type = "PLAIN_AXES"
        dof_obj.empty_display_size = dof_size
        dof_obj.location           = dof_loc
        coll.objects.link(dof_obj)

        # Bezier circle path — centred at cursor
        path_obj = _make_bezier_circle(
            name=f"Path_TCamera_{n}",
            radius=radius,
            location=cursor_loc,
        )
        coll.objects.link(path_obj)

        # Camera — location (0, 0, 0): Follow Path drives the world position
        cam_data              = bpy.data.cameras.new(f"TCamera_{n}")
        cam_data.display_size = cam_size
        cam_data.dof.use_dof      = True
        cam_data.dof.focus_object = dof_obj

        cam_obj          = bpy.data.objects.new(f"TCamera_{n}", cam_data)
        cam_obj.location = Vector((0.0, 0.0, 0.0))
        coll.objects.link(cam_obj)

        # ── Constraints (order matters: Follow Path evaluated before Track To) ──

        # 1. Follow Path — controls camera position along the circle
        follow                  = cam_obj.constraints.new(type="FOLLOW_PATH")
        follow.target           = path_obj
        follow.use_curve_follow = False   # Track To handles rotation

        # 2. Track To — controls where the camera points
        track            = cam_obj.constraints.new(type="TRACK_TO")
        track.target     = target_obj
        track.track_axis = "TRACK_NEGATIVE_Z"
        track.up_axis    = "UP_Y"

        # Leave camera selected and active
        for obj in context.selected_objects:
            obj.select_set(False)
        cam_obj.select_set(True)
        context.view_layer.objects.active = cam_obj

        self.report(
            {"INFO"},
            f"Created TCamera_{n} with Follow Path (r={radius:.4f}) "
            f"→ Target_Camera_{n} | DoF: DoF_Camera_{n} | Path: Path_TCamera_{n}",
        )
        return {"FINISHED"}


# ── Menu integration ──────────────────────────────────────────

def _menu_func(self, context):
    layout = self.layout
    layout.separator()
    layout.operator(
        OBJECT_OT_add_tracked_camera.bl_idname,
        text="Tracked Camera",
        icon="CAMERA_DATA",
    )
    layout.operator(
        OBJECT_OT_add_tracked_path_camera.bl_idname,
        text="Tracked Camera + Follow Path",
        icon="CAMERA_DATA",
    )


# ── Registration ──────────────────────────────────────────────

_classes = (
    CreateTrackedCamerasPreferences,
    PREFERENCES_OT_ctc_save_ini,
    PREFERENCES_OT_ctc_load_ini,
    OBJECT_OT_add_tracked_camera,
    OBJECT_OT_add_tracked_path_camera,
)


def _load_prefs_from_ini_delayed():
    """
    Called by a timer shortly after registration, once
    bpy.context.preferences is fully available.
    Reads the INI file and pushes all values into the add-on preferences.
    Returns None so the timer does not repeat.
    """
    try:
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        if addon is None:
            return None
        values = load_ini_values()
        p = addon.preferences
        p.target_empty_size   = values["target_empty_size"]
        p.camera_display_size = values["camera_display_size"]
        p.dof_empty_size      = values["dof_empty_size"]
        p.camera_distance     = values["camera_distance"]
        p.use_collection      = values["use_collection"]
        p.circle_radius       = values["circle_radius"]
    except Exception as exc:
        print(f"[CreateTrackedCameras] Could not load INI on startup: {exc}")
    return None


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    if hasattr(bpy.types, "VIEW3D_MT_camera_add"):
        bpy.types.VIEW3D_MT_camera_add.append(_menu_func)
    else:
        bpy.types.VIEW3D_MT_add.append(_menu_func)

    bpy.app.timers.register(_load_prefs_from_ini_delayed, first_interval=0.5)


def unregister():
    if hasattr(bpy.types, "VIEW3D_MT_camera_add"):
        bpy.types.VIEW3D_MT_camera_add.remove(_menu_func)
    else:
        bpy.types.VIEW3D_MT_add.remove(_menu_func)

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
