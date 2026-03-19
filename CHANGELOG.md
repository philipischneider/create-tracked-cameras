# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.1.0] — 2026-03-19

### Added
- **Tracked Camera + Follow Path** preset: creates a camera on a Bezier-circle
  orbit path with Follow Path stacked before Track To.
- **Collection grouping** option: all rig objects can be wrapped inside a
  `TCamera_N` collection (toggle in preferences, persisted to INI).
- `circle_radius` preference (default 250 mm) for the Follow Path orbit path.
- `blender_manifest.toml` for compatibility with the Blender 4.2+ extension
  system.

### Fixed
- Bezier circle: North and South control-point handles were swapped, producing
  a figure-eight shape instead of a circle.

---

## [1.0.0] — 2026-03-19

### Added
- Initial release.
- **Tracked Camera** preset: camera + Track To constraint + target empty at
  3D cursor + Depth of Field focus empty at the midpoint.
- INI-backed preferences stored in the user's home directory.
- **Save to INI / Load from INI** buttons in the preferences panel.
- Settings auto-loaded from INI on add-on registration via a deferred timer.
- Compatible with Blender 5.0+.
