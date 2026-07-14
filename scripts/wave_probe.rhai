// wave_probe.rhai — CPU/GPU wave parity check.
//
// Pins this entity to ocean_height() at a slowly orbiting point near the
// raft. The buoy must sit exactly on the rendered water surface at all
// times; if it floats above or sinks below, the CPU sampler and the GPU
// vertex displacement have diverged and buoyancy can't be trusted.

const ORBIT_RADIUS = 6.0;
const ORBIT_SPEED = 0.12;   // rad/s — slow drift so parity is easy to eyeball

fn on_update() {
    let t = total_time();
    let x = cos(t * ORBIT_SPEED) * ORBIT_RADIUS;
    let z = sin(t * ORBIT_SPEED) * ORBIT_RADIUS + 4.0;
    let h = ocean_height(x, z);
    set_position(this_entity(), x, h, z);
}
