// legs_idle.rhai — pins the player's legs to the scooting raft seat and
// adds a gentle idle sway (calves drifting with the water) plus a small
// drag response to the raft's roll.
//
// The seat's raft-local position and outward heading are read from the
// seat component every frame (seat_camera.rhai computes the perimeter
// path once and publishes seat_x / seat_z / seat_out_deg), then composed
// with the raft transform here — the eye and the body can never drift
// apart, on any edge. set_field is deferred, so the values are at most
// one frame old (~7 mm at full scoot speed) and DON'T EXIST until the
// seat's first publish flushes — hence the unit-value guard below.

const SEAT_Y = 0.30;    // hip height above raft origin (deck 0.26 + cushion)
const INSET = 0.03;     // hips sit just inside the eye's edge path
const SWAY_DEG = 2.2;   // idle sway amplitude
const SWAY_RATE = 2.4;  // rad/s — slow pendulum

fn on_update() {
    let raft = get_entity("raft");
    let seat = get_entity("seat_camera");
    if raft < 0 || seat < 0 { return; }

    let out_deg = get_field(seat, "seat", "seat_out_deg");
    if out_deg == () { return; }   // seat hasn't published yet (first frames)
    let psi = deg_to_rad(out_deg);
    // Pull the hips slightly inboard, opposite the outward heading.
    let lx = get_field(seat, "seat", "seat_x") - sin(psi) * INSET;
    let lz = get_field(seat, "seat", "seat_z") - cos(psi) * INSET;
    let ly = SEAT_Y;

    let rp = get_position(raft);
    let rr = get_rotation(raft);
    let ax = deg_to_rad(rr["x"]);
    let ay = deg_to_rad(rr["y"]);
    let az = deg_to_rad(rr["z"]);

    let sx = sin(ax); let cx = cos(ax);
    let sy = sin(ay); let cy = cos(ay);
    let sz = sin(az); let cz = cos(az);

    // Seat offset through the raft rotation matrix (R = Rz·Ry·Rx).
    let px = rp["x"] + (cy * cz) * lx + (sx * sy * cz - cx * sz) * ly + (cx * sy * cz + sx * sz) * lz;
    let py = rp["y"] + (cy * sz) * lx + (sx * sy * sz + cx * cz) * ly + (cx * sy * sz - sx * cz) * lz;
    let pz = rp["z"] + (-sy) * lx + (sx * cy) * ly + (cx * cy) * lz;

    set_position(this_entity(), px, py, pz);

    // Legs face seat-outward and inherit the raft attitude, plus idle
    // sway and a water-drag lean opposing the roll (your calves lag
    // behind the deck). Euler order is Rz·Ry·Rx, so the sway on X is the
    // innermost rotation — it swings the calves around the knee axis of
    // the MODEL's frame, correct on every edge.
    let sway = sin(total_time() * SWAY_RATE) * SWAY_DEG;
    set_rotation(
        this_entity(),
        rr["x"] + sway,
        rr["y"] + out_deg,
        rr["z"] * 0.6
    );
}
