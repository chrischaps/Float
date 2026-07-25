// wave_probe.rhai — CPU/GPU wave parity check.
//
// Pins this entity to ocean_height() at a slowly orbiting point near the
// raft. The buoy must sit exactly on the rendered water surface at all
// times; if it floats above or sinks below, the CPU sampler and the GPU
// vertex displacement have diverged and buoyancy can't be trusted.
//
// Hidden by default: the ocean component's `show_probe` (F3 Ocean Debug →
// Diagnostics → "Wave probe buoy") parks it deep underwater when false —
// there is no engine-side model hide, and turbidity extinguishes it long
// before 60 m down.

const ORBIT_RADIUS = 6.0;
const ORBIT_SPEED = 0.12;   // rad/s — slow drift so parity is easy to eyeball
const PARK_Y = -60.0;

fn on_update() {
    // Guarded read: unit until the field materializes on the first frames.
    let show = get_field(get_entity("ocean"), "ocean", "show_probe");
    if show.type_of() != "bool" || !show {
        set_position(this_entity(), 0.0, PARK_Y, 0.0);
        return;
    }
    let t = total_time();
    let x = cos(t * ORBIT_SPEED) * ORBIT_RADIUS;
    let z = sin(t * ORBIT_SPEED) * ORBIT_RADIUS + 4.0;
    let h = ocean_height(x, z);
    set_position(this_entity(), x, h, z);
}
