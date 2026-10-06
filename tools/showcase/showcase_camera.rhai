// showcase_camera.rhai: external cameras for showcase captures.
//
// tools/showcase/cap.py copies this to scripts/_cap_<shot>_camera.rhai with
// the PARAMS block filled in, and patches a temp copy of seat_camera.rhai so
// it stops writing the camera. Never used in play.
//
// Modes (mode):
//   1 rig    a camera boat at a fixed offset from the raft (dist, az_deg
//            from +Z toward +X, height), optionally orbiting at orbit_rate
//            deg/s and dollying dist/height toward dist1/height1 over dolly_s
//   2 fixed  at world (fx, fy, fz)
//   3 sun    the rig, but its azimuth stays opposite the sun (+ sun_off_deg),
//            looking through the raft toward the light all day
//   4 pair   frames the raft and `pair_name` together: the camera sits off
//            their midpoint, side-on to the line between them (falls back to
//            the rig while the other raft is parked below the sea)
// ride: how much of the local wave height the camera rides (a boat, not a
// tripod); look_ride: how much of the raft's heave the gaze follows (0 keeps
// the horizon still so the raft visibly rises and falls in frame).

// >>> PARAMS
let mode = 1;
let dist = 9.0;
let dist1 = -1.0;
let height = 2.0;
let height1 = -1.0;
let dolly_s = 30.0;
let az_deg = 200.0;
let orbit_rate = 0.0;
let sun_off_deg = 12.0;
let fx = 0.0;
let fy = 2.0;
let fz = 0.0;
let look_y = 0.4;
let look_dx = 0.0;
let look_dz = 0.0;
let ride = 0.6;
let look_ride = 0.3;
let fov = 50.0;
let lag = 1.5;
let pair_name = "raft2";
let pair_side = 1.0;
let pair_back = 0.0;
let pair_anchor = 0.5;   // camera base: 0 = our raft, 0.5 = midpoint
let pair_mix = 0.5;      // gaze: fraction of the way from our raft to the other
// <<< PARAMS

let t = 0.0;
let started = false;
let az = 0.0;
let wy = 0.0;
let ry = 0.0;
let px = 0.0;
let pz = 0.0;
let plx = 0.0;
let plz = 0.0;
let pair_on = false;

fn on_update() {
    let dt = delta_time();
    let raft = get_entity("raft");
    if raft < 0 { return; }
    let p = get_position(raft);
    let rx = p["x"];
    let rz = p["z"];
    t += dt;

    let target_az = az_deg + orbit_rate * t;
    if mode == 3 {
        let sun = get_entity("sun");
        if sun >= 0 {
            let d = get_field(sun, "light", "direction");
            if d != () {
                // camera opposite the light: direction points toward the sun
                target_az = atan2(-d[0], -d[2]) * 180.0 / PI() + sun_off_deg;
            }
        }
    }
    if !started {
        az = target_az;
    } else {
        let da = target_az - az;
        while da > 180.0 { da -= 360.0; }
        while da < -180.0 { da += 360.0; }
        az += da * clamp(lag * dt, 0.0, 1.0);
    }

    let k = if dolly_s > 0.0 { clamp(t / dolly_s, 0.0, 1.0) } else { 1.0 };
    k = k * k * (3.0 - 2.0 * k);
    let dd = if dist1 > 0.0 { dist + (dist1 - dist) * k } else { dist };
    let hh = if height1 > 0.0 { height + (height1 - height) * k } else { height };

    let a = az * PI() / 180.0;
    let cx = rx + sin(a) * dd;
    let cz = rz + cos(a) * dd;
    let base_y = hh;
    let lx = rx + look_dx;
    let lz = rz + look_dz;
    if mode == 2 {
        cx = fx;
        cz = fz;
        base_y = fy;
    } else if mode == 4 {
        let o = get_entity(pair_name);
        if o >= 0 {
            let q = get_position(o);
            if q["y"] > -10.0 {
                let vx = q["x"] - rx;
                let vz = q["z"] - rz;
                let n = sqrt(vx * vx + vz * vz) + 0.001;
                let bx = rx + vx * pair_anchor;
                let bz = rz + vz * pair_anchor;
                let mx = rx + vx * pair_mix;
                let mz = rz + vz * pair_mix;
                let tx = bx + (-vz / n) * dd * pair_side - (vx / n) * pair_back;
                let tz = bz + (vx / n) * dd * pair_side - (vz / n) * pair_back;
                if !pair_on { px = tx; pz = tz; plx = mx; plz = mz; pair_on = true; }
                let k2 = clamp(0.6 * dt, 0.0, 1.0);
                px += (tx - px) * k2;
                pz += (tz - pz) * k2;
                plx += (mx - plx) * k2;
                plz += (mz - plz) * k2;
                cx = px;
                cz = pz;
                lx = plx;
                lz = plz;
            }
        }
    }

    // Ride the swell like a small boat; smooth so chop doesn't shake it.
    let h = ocean_height(cx, cz);
    let s = clamp(2.0 * dt, 0.0, 1.0);
    let ry_now = p["y"];
    if !started { wy = h; ry = ry_now; started = true; }
    wy += (h - wy) * s;
    ry += (ry_now - ry) * clamp(4.0 * dt, 0.0, 1.0);
    let cy = base_y + ride * wy;
    // Never below the local surface (the underside of the sea is not a look).
    if cy < h + 0.6 { cy = h + 0.6; }

    set_camera_position(cx, cy, cz);
    set_camera_target(lx, look_y + look_ride * ry, lz);
    set_camera_fov(fov);
}
