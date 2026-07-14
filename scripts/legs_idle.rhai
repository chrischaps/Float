// legs_idle.rhai — pins the player's legs to the raft seat and adds a
// gentle idle sway (calves drifting with the water) plus a small drag
// response to the raft's roll. The legs entity is positioned every frame
// from the raft transform — same composition as seat_camera.rhai, so the
// eye and the body can never drift apart.

const SEAT_Y = 0.30;    // hip height above raft origin (deck 0.26 + cushion)
const SEAT_Z = 1.02;    // just inside the +Z edge
const SWAY_DEG = 2.2;   // idle sway amplitude
const SWAY_RATE = 2.4;  // rad/s — slow pendulum

fn on_update() {
    let raft = get_entity("raft");
    if raft < 0 { return; }

    let rp = get_position(raft);
    let rr = get_rotation(raft);
    let ax = deg_to_rad(rr["x"]);
    let ay = deg_to_rad(rr["y"]);
    let az = deg_to_rad(rr["z"]);

    let sx = sin(ax); let cx = cos(ax);
    let sy = sin(ay); let cy = cos(ay);
    let sz = sin(az); let cz = cos(az);

    // Seat offset through the raft rotation matrix (R = Rz·Ry·Rx).
    let ly = SEAT_Y;
    let lz = SEAT_Z;
    let px = rp["x"] + (sx * sy * cz - cx * sz) * ly + (cx * sy * cz + sx * sz) * lz;
    let py = rp["y"] + (sx * sy * sz + cx * cz) * ly + (cx * sy * sz - sx * cz) * lz;
    let pz = rp["z"] + (sx * cy) * ly + (cx * cy) * lz;

    set_position(this_entity(), px, py, pz);

    // Legs inherit the raft attitude, plus idle sway and a water-drag lean
    // opposing the roll (your calves lag behind the deck).
    let sway = sin(total_time() * SWAY_RATE) * SWAY_DEG;
    set_rotation(
        this_entity(),
        rr["x"] + sway,
        rr["y"],
        rr["z"] * 0.6
    );
}
