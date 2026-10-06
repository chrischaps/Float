"""Shot list for tools/showcase/cap.py (the chaps.dev Float page).

Each shot: t=(t0, t1) game seconds to capture; set=[(table, field, value)];
camera={...showcase_camera.rhai params} for an external view (omit = the
first-person seat); input="time action ...;..." (input_script.rhai format);
fps (30); step (game s per frame, default 1/fps); title (keep the card).
"""

TOD = "entities.tod.time_of_day"
WX = "entities.weather_controller.weather"
CALM = "entities.dead_calm_controller.dead_calm"
REAL = "entities.reality_controller.reality"
VIS = "entities.raft_visitor.raft_visitor"
WHALE = "entities.whale.whale"
BIO = "entities.biolum_controller.biolum"
SEAT = "entities.seat_camera.seat"


def tod(hour, day=4.0, length=600.0, advance=True):
    """Start the clock at `hour` on `day` (>= 4 is past the opening ramp)."""
    return [(TOD, "time_hours", float(hour)), (TOD, "last_hours", float(hour)),
            (TOD, "day", float(day)), (TOD, "day_length_sec", float(length)),
            (TOD, "auto_advance", advance)]


def weather(state):
    """Hold a weather state from the first frame (forced + snapped)."""
    return [(WX, "forced_state", float(state)), (WX, "state", float(state)), (WX, "snap", True)]


def ease(axis, t0, t1, peak, step=1.0 / 30.0):
    """A stick move that eases in and out: half a sine from t0 to t1."""
    import math
    out, t = [], t0
    while t < t1:
        v = peak * math.sin(math.pi * (t - t0) / (t1 - t0))
        out.append("%.3f axis %s %.3f" % (t, axis, v))
        t += step
    out.append("%.3f axis %s 0" % (t1, axis))
    return ";".join(out)


def moves(*parts):
    return ";".join(parts)


QUIET = [(REAL, "enabled", False), (CALM, "enabled", False), (VIS, "enabled", False)]

SHOTS = {
    # Hero: one day, pre-dawn to first stars, from a camera boat that keeps
    # the sun behind the raft. 48 s days: 2 s a game hour, waves at true speed.
    "day": dict(
        t=(1.0, 40.0),
        set=tod(4.6, length=48.0) + weather(1) + QUIET
            + [(BIO, "chance", 1.0), (BIO, "earliest", 20.8), (WHALE, "bearing_spread_deg", 6.0)],
        camera=dict(mode=3, dist=9.5, height=3.0, sun_off_deg=14.0, look_y=1.2,
                    look_ride=0.5, ride=0.4, fov=46.0, lag=0.8),
    ),
    # The seat: first person, looking down past the knees, up to the
    # horizon, and a scoot along the edge.
    "seat": dict(
        t=(1.0, 17.0),
        set=tod(9.5) + weather(0) + QUIET,
        input=moves(ease("RightStickY", 2.0, 3.4, -0.3), ease("RightStickY", 5.4, 6.8, 0.3),
                    ease("RightStickX", 7.4, 9.4, -0.4), "9.6 down KeyA", "12.6 up KeyA",
                    ease("RightStickX", 13.4, 15.6, 0.45)),
    ),
    # The deck hesitates: a heavy swell, side-on and low, real time.
    "swell": dict(
        t=(2.0, 18.0),
        set=tod(15.5) + weather(2.6) + QUIET,
        camera=dict(mode=1, dist=7.5, az_deg=250.0, height=1.3, look_y=0.5,
                    look_ride=0.0, ride=0.5, fov=42.0),
    ),
    # Weather: a storm from the seat. Rain streaks, impact rings, lightning.
    "storm": dict(
        t=(1.5, 19.5),
        set=tod(15.0) + weather(4) + QUIET
            + [(WX, "strike_min_s", 2.0), (WX, "strike_max_s", 6.0), (WX, "near_strike_chance", 0.5)],
        input=moves(ease("RightStickX", 7.0, 12.0, -0.3)),
    ),
    # Dead calm: the sea collapses to a star mirror in eight seconds.
    "calm": dict(
        t=(1.0, 19.0),
        set=tod(5.0) + weather(0) + [(REAL, "enabled", False), (VIS, "enabled", False),
                                     (CALM, "trigger_calm", 1.0), (BIO, "chance", 0.0)],
        camera=dict(mode=3, dist=8.0, sun_off_deg=24.0, height=1.3, look_y=2.2,
                    look_ride=0.2, ride=0.5, fov=58.0),
    ),
    # The whale: dusk breach toward the sunset band, raft in the foreground.
    "whale": dict(
        t=(0.5, 12.0),
        set=tod(19.12) + weather(0) + QUIET
            + [(WHALE, "window_start", 19.15), (WHALE, "window_end", 19.25),
               (WHALE, "bearing_spread_deg", 0.0), (WHALE, "encore_chance", 1.0)],
        camera=dict(mode=1, dist=20.0, az_deg=88.0, height=2.2, look_y=3.0,
                    look_dx=-40.0, look_dz=0.0, look_ride=0.0, ride=0.5, fov=23.0),
    ),
    # Reality tears (one shot per mode, cut together).
    "tear_matrix": dict(
        t=(0.3, 8.0),
        set=tod(10.0) + weather(1) + [(CALM, "enabled", False), (VIS, "enabled", False),
                                      (REAL, "trigger_mode", 1.0)],
        camera=dict(mode=1, dist=8.0, az_deg=200.0, height=1.8, look_y=0.9, fov=50.0),
    ),
    "tear_blood": dict(
        t=(0.3, 8.0),
        set=tod(19.0) + weather(1) + [(CALM, "enabled", False), (VIS, "enabled", False),
                                      (REAL, "trigger_mode", 2.0)],
        camera=dict(mode=1, dist=8.0, az_deg=100.0, height=1.8, look_y=0.9, fov=50.0),
    ),
    "tear_drunk": dict(
        t=(1.0, 9.0),
        set=tod(11.0) + weather(1) + [(CALM, "enabled", False), (VIS, "enabled", False),
                                      (REAL, "trigger_mode", 3.0)],
    ),
    "tear_tron": dict(
        t=(0.3, 8.0),
        set=tod(22.0) + weather(0) + [(CALM, "enabled", False), (VIS, "enabled", False),
                                      (REAL, "trigger_mode", 4.0)],
        camera=dict(mode=1, dist=8.0, az_deg=200.0, height=1.8, look_y=0.9, fov=50.0),
    ),
    # Under: a big sea buries the eye.
    "under": dict(
        t=(1.0, 60.0),
        set=tod(13.0) + weather(4) + QUIET + [(WX, "strike_min_s", 30.0), (WX, "strike_max_s", 60.0)],
        preview_every=0.25,
    ),
    # Underwater moment still: the seat's debug one-shot holds the eye 0.4 m
    # under (the same render path a swell takes; real dunks are a frame-luck
    # of the gusty storm sea and don't reproduce run to run).
    "under_still": dict(
        still=True, t=(2.5, 2.5), size=(1920, 1080),
        set=tod(13.5) + weather(3) + QUIET + [(SEAT, "force_submerge_s", 4.0)],
    ),
    # The visitor: a second raft holding off the beam.
    "visitor": dict(
        t=(92.0, 112.0),
        set=tod(11.6) + weather(1) + [(REAL, "enabled", False), (CALM, "enabled", False),
                                      (VIS, "trigger_visit", 1.0)],
        camera=dict(mode=4, dist=2.5, pair_back=7.0, pair_anchor=0.0, pair_mix=0.75,
                    az_deg=240.0, height=2.6, look_y=0.5, look_ride=0.0, fov=40.0),
        preview_every=2.0,
    ),
}


# Cover: one frozen instant of sea, lit at seven hours. Everything random is
# off (weather's gusts reshape the spectrum, idle fidgets move the body, birds
# and blooms come and go), so every slice holds the same waves and pose and
# only the light changes. tools/showcase/cover.py cuts them into strips.
COVER_HOURS = [5.3, 6.4, 9.5, 13.0, 17.6, 19.05, 20.6, 23.0]
COVER_T = 20.0
COVER_CAM = dict(mode=1, dist=7.5, az_deg=70.0, height=2.2, look_y=1.3, look_ride=0.5,
                 ride=0.0, fov=38.0)
for _i, _h in enumerate(COVER_HOURS):
    for _tag, _az in (("", 100.0),):
        SHOTS["slice%s_%d" % (_tag, _i)] = dict(
            still=True, t=(COVER_T, COVER_T),
            set=tod(_h, advance=False) + QUIET
                + [(WX, "enabled", False), (BIO, "chance", 0.0), (WHALE, "enabled", False),
                   ("entities.bird_flock.birds", "enabled", False),
                   ("entities.body.idle_brain", "enabled", False)],
            camera=dict(COVER_CAM, az_deg=_az),
            # scoot round to the +X (sunset-facing) edge before the instant
            input="1.0 down KeyA;12.0 up KeyA",
        )
