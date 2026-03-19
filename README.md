# Create Tracked Cameras

A Blender add-on (compatible with **Blender 5.0 and later**) that adds two
ready-to-use camera presets to the **Shift+A** add menu:

| Preset | What it creates |
|--------|-----------------|
| **Tracked Camera** | Camera + Track To target empty + Depth of Field focus empty |
| **Tracked Camera + Follow Path** | All of the above, plus a Bezier-circle orbit path with a Follow Path constraint |

All default values (sizes, distances, radius) are configurable through
**Edit → Preferences → Add-ons → Create Tracked Cameras** and persisted in a
plain-text **INI file** stored in the user's home directory.

---

## Features

- **One-click camera setup** — every object needed for a professional
  track-and-focus rig is created automatically and named consistently.
- **Track To constraint** — the camera always looks at `Target_Camera_N`
  (−Z toward target, Y up, matching Blender defaults).
- **Depth of Field** — enabled by default; the focus object is a dedicated
  `DoF_Camera_N` empty placed between the camera and the target.
- **Follow Path (optional preset)** — adds a closed Bezier-circle path
  (`Path_TCamera_N`) centred on the 3D cursor. The Follow Path constraint is
  stacked *before* Track To so the constraint evaluation order is correct.
- **Collection grouping** — optionally wraps every new rig inside a collection
  named after the camera (toggle in preferences, persisted to INI).
- **INI-backed preferences** — default values survive across Blender sessions
  and machines; easy to version-control or share across a team.
- **No bpy.ops dependencies** — object creation uses `bpy.data` directly for
  reliable behaviour regardless of viewport state.

---

## Requirements

- Blender **5.0** or newer
- No third-party Python packages required

---

## Installation

The add-on is structured as a Python package so it is compatible with both
the **Blender Extension system** (4.2+) and the **legacy add-on installer**.

### Blender Extension — recommended (Blender 4.2+)

1. Download the zipped release (the zip contains `__init__.py` and
   `blender_manifest.toml` at the root).
2. In Blender: **Edit → Preferences → Extensions → Install from Disk…**
3. Select the zip file. Blender installs it under the name defined in the
   manifest (`create_tracked_cameras`).

### Legacy add-on installer (any Blender 5.0+ version)

1. Download the zipped release.
2. In Blender: **Edit → Preferences → Add-ons → Install from File…**
3. Select the zip file and click **Install Add-on**.
4. Enable the add-on by ticking the checkbox next to *Create Tracked Cameras*.

---

## Usage

### Tracked Camera

1. Move the **3D Cursor** to the desired target position
   (*Shift+Right-click* or **Object → Snap → Cursor to …**).
2. Press **Shift+A** in the 3D Viewport.
3. Click **Tracked Camera**.

**Objects created:**

| Object | Name | Description |
|--------|------|-------------|
| Empty | `Target_Camera_N` | Track To target — placed at the 3D cursor |
| Empty | `DoF_Camera_N` | Depth of Field focus object — placed at the midpoint between target and camera |
| Camera | `TCamera_N` | Camera with Track To + DoF already configured |

The camera is offset from the target by **Camera Distance** along the Y axis
and is immediately selected and active.

---

### Tracked Camera + Follow Path

1. Move the **3D Cursor** to the centre of the desired orbit.
2. Press **Shift+A → Tracked Camera + Follow Path**.

**Additional object created:**

| Object | Name | Description |
|--------|------|-------------|
| Curve | `Path_TCamera_N` | Closed Bezier circle centred on the 3D cursor |

The camera's world location is set to `(0, 0, 0)`; its position in the scene
is driven entirely by the **Follow Path** constraint.
To animate the orbit, keyframe the curve's **Evaluation Time**
(*Object Data Properties → Path Animation → Evaluation Time*) or use
**Object → Animation → Animate Path** on the path object.

**Constraint stack order on the camera:**

```
1. Follow Path  →  controls world position along the circle
2. Track To     →  controls rotation to face Target_Camera_N
```

---

## Configuration

### Preferences panel

Open **Edit → Preferences → Add-ons → Create Tracked Cameras**.

| Setting | Default | Description |
|---------|---------|-------------|
| Target Empty Size | 10 mm | Viewport display size of `Target_Camera_N` |
| DoF Empty Size | 10 mm | Viewport display size of `DoF_Camera_N` |
| Camera Display Size | 25 mm | Camera frustum display size in the viewport |
| Camera Distance | 50 mm | Offset from target to camera (Tracked Camera only) |
| Create Collection per Camera | Off | Groups all rig objects in a `TCamera_N` collection |
| Circle Radius | 250 mm | Radius of the orbit path (Follow Path preset) |

Click **Save to INI** to write the current values to disk, or **Load from INI**
to restore them from disk.

### INI file

The configuration file is created automatically on first save:

| Platform | Default path |
|----------|-------------|
| Windows | `C:\Users\<user>\create_tracked_cameras.ini` |
| macOS / Linux | `~/create_tracked_cameras.ini` |

Example content:

```ini
[Settings]
target_empty_size = 0.010000
camera_display_size = 0.025000
dof_empty_size = 0.010000
camera_distance = 0.050000
use_collection = 0
circle_radius = 0.250000
```

> **Note:** all length values are in **metres** (Blender's internal unit).
> 10 mm = 0.010, 250 mm = 0.250, etc.

The INI is read automatically every time the add-on loads (via a 0.5-second
deferred timer so it runs after Blender's preference system is fully
initialised).

---

## Object naming convention

The integer suffix `N` is the lowest positive integer not already used by a
`TCamera_N` object in the current `.blend` file, so numbers are always unique
and never reused within a session.

| Object | Naming pattern |
|--------|----------------|
| Camera | `TCamera_N` |
| Track To target | `Target_Camera_N` |
| Depth of Field focus | `DoF_Camera_N` |
| Orbit path | `Path_TCamera_N` |
| Collection (optional) | `TCamera_N` |

---

## License

[GNU GPLv3](LICENSE) — free to use, modify, and distribute under GNU General Public License version 3.
