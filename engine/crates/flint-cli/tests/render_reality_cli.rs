//! The reality styles (#746) side by side, end to end through `flint render`.
//! The five share one pass's code (`stylize/reality.rs`), each with its own
//! uniform buffer; their uniform bind group was kept under one name, so the
//! first one drawn lent its buffer to every other and `underwater` beside
//! `drunk` drew drunk's numbers: nothing. Skips itself without a GPU.

use std::path::{Path, PathBuf};
use std::process::Output;

const FLINT: &str = env!("CARGO_BIN_EXE_flint");
const WIDTH: u32 = 320;
const HEIGHT: u32 = 180;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn dir(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("render_reality_cli")
        .join(name);
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// The plain bench the `reality-*` goldens draw on, with `styles` on.
fn render(dir: &Path, name: &str, styles: &[&str]) -> (Output, PathBuf) {
    let out = dir.join(format!("{name}.png"));
    let mut cmd = std::process::Command::new(FLINT);
    cmd.arg("render")
        .arg(repo().join("tests/fixtures/scenes/stylize_props_plain.scene.toml"))
        .args(["--width", &WIDTH.to_string()])
        .args(["--height", &HEIGHT.to_string()])
        .arg("--no-grid");
    for s in styles {
        cmd.args(["--style", s]);
    }
    let run = cmd.arg("-o").arg(&out).output().expect("run flint");
    (run, out)
}

fn stderr(o: &Output) -> String {
    String::from_utf8_lossy(&o.stderr).into_owned()
}

fn no_gpu(o: &Output) -> bool {
    let missing = !o.status.success() && stderr(o).contains("headless render context");
    if missing {
        eprintln!("no GPU adapter: skipped");
    }
    missing
}

fn ok(o: &Output) {
    assert!(o.status.success(), "flint failed: {}", stderr(o));
}

/// Mean absolute difference over every channel, in levels.
fn mean_diff(a: &Path, b: &Path) -> f64 {
    let (a, b) = (image::open(a).unwrap().to_rgb8(), image::open(b).unwrap().to_rgb8());
    let sum: u64 = a
        .as_raw()
        .iter()
        .zip(b.as_raw())
        .map(|(x, y)| x.abs_diff(*y) as u64)
        .sum();
    sum as f64 / a.as_raw().len() as f64
}

const UNDERWATER: &str = "underwater:blend=1,depth=0.4,churn=0.3,daylight=1";

#[test]
fn underwater_draws_its_own_numbers_beside_another_reality_style() {
    let dir = dir("beside");
    let (run, plain) = render(&dir, "plain", &[]);
    if no_gpu(&run) {
        return;
    }
    ok(&run);
    let (run, alone) = render(&dir, "alone", &[UNDERWATER]);
    ok(&run);
    let drawn = mean_diff(&plain, &alone);
    assert!(drawn > 5.0, "underwater alone should change the bench: {drawn:.2}");

    // A faint second reality style, listed first and last: underwater must
    // still be underwater (main drew the plain bench here, 0.2 from `plain`)
    for (name, styles) in [
        ("drunk_first", vec!["drunk:blend=0.05", UNDERWATER]),
        ("drunk_after", vec![UNDERWATER, "drunk:blend=0.05"]),
        ("tron", vec![UNDERWATER, "tron:blend=0.05"]),
    ] {
        let (run, both) = render(&dir, name, &styles);
        ok(&run);
        let off = mean_diff(&alone, &both);
        eprintln!("{name}: {off:.2} from underwater alone, {drawn:.2} from plain");
        assert!(
            off < drawn * 0.25,
            "{name}: underwater beside another reality style is {off:.2} levels from \
             underwater alone (underwater alone is {drawn:.2} from the plain bench)"
        );
    }
}
