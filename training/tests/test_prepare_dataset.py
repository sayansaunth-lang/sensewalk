import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_dataset import (  # noqa: E402
    cluster_by_similarity,
    dhash64,
    hamming,
    parse_label_file,
    prepare,
    Sample,
)


def make_pattern_image(seed: int, size=(96, 128)) -> np.ndarray:
    """A structured (not pure-noise) image so perceptual hashes behave like
    they do on real photos: distinct seeds differ, brightness-shifted copies match."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size[0], size[1], 3), np.uint8)
    for _ in range(12):
        x, y = int(rng.integers(0, size[1] - 20)), int(rng.integers(0, size[0] - 20))
        w, h = int(rng.integers(10, 50)), int(rng.integers(10, 40))
        color = tuple(int(v) for v in rng.integers(30, 255, 3))
        cv2.rectangle(img, (x, y), (min(x + w, size[1] - 1), min(y + h, size[0] - 1)), color, -1)
    return img


def write_source(root: Path, items: list[tuple[str, np.ndarray, str]]) -> None:
    (root / "train" / "images").mkdir(parents=True)
    (root / "train" / "labels").mkdir(parents=True)
    for stem, img, label in items:
        cv2.imwrite(str(root / "train" / "images" / f"{stem}.jpg"), img)
        (root / "train" / "labels" / f"{stem}.txt").write_text(label)


GOOD = "0 0.5 0.5 0.2 0.2\n"


def test_parse_label_file_drops_malformed_and_junk(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text(
        "0 0.5 0.5 0.2 0.2\n"        # valid
        "Dear Hiring Manager\n"        # junk text (real-world occurrence)
        "0 0.5 0.5\n"                  # too few fields
        "0 1.5 0.5 0.2 0.2\n"          # out of range
        "0 0.5 0.5 0.0 0.2\n"          # zero width
        "7 0.5 0.5 0.2 0.2\n"          # unknown class
        "\n"
    )
    boxes, dropped = parse_label_file(p, {"0": 0})
    assert boxes == [(0, 0.5, 0.5, 0.2, 0.2)]
    assert dropped == 5


def test_dhash_matches_brightened_copy_but_not_different_image():
    base = make_pattern_image(1)
    brighter = np.clip(base.astype(int) + 20, 0, 255).astype(np.uint8)
    other = make_pattern_image(2)
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        for name, im in (("a", base), ("b", brighter), ("c", other)):
            cv2.imwrite(f"{d}/{name}.png", im)
        ha, hb, hc = (dhash64(Path(f"{d}/{n}.png")) for n in "abc")
    assert hamming(ha, hb) <= 6
    assert hamming(ha, hc) > 6


def test_cluster_groups_near_duplicates():
    samples = [Sample("s", Path("x"), [], dhash=0b0), Sample("s", Path("y"), [], dhash=0b11), Sample("s", Path("z"), [], dhash=(1 << 64) - 1)]
    clusters = cluster_by_similarity(samples)
    assert sorted(len(c) for c in clusters) == [1, 2]


def test_prepare_end_to_end_no_leakage_and_cleaning(tmp_path):
    src = tmp_path / "src"
    items = []
    # 30 distinct source images, each with a brightness-augmented copy
    for i in range(30):
        base = make_pattern_image(100 + i)
        items.append((f"img{i}", base, GOOD))
        items.append((f"img{i}_aug", np.clip(base.astype(int) + 15, 0, 255).astype(np.uint8), GOOD))
    # one image whose only label line is junk -> must be dropped entirely
    items.append(("junk", make_pattern_image(999), "Dear Sir, thank you for your time\n"))
    write_source(src, items)

    out = tmp_path / "out"
    report = prepare({"s": src}, out, ["pothole"], seed=3)

    assert report.images_dropped_no_valid_boxes == 1
    assert report.label_lines_dropped >= 1
    assert report.images_kept == 60
    assert (out / "data.yaml").exists()
    assert "nc: 1" in (out / "data.yaml").read_text()

    # No leakage: re-hash everything per split; no cross-split pair may be near-duplicate.
    hashes = {}
    for split in ("train", "val", "test"):
        hashes[split] = [dhash64(p) for p in (out / "images" / split).glob("*.jpg")]
    for a in ("train", "val", "test"):
        for b in ("train", "val", "test"):
            if a >= b:
                continue
            for ha in hashes[a]:
                for hb in hashes[b]:
                    assert hamming(ha, hb) > 6, f"near-duplicate leaked between {a} and {b}"

    # every image has a label file in the same split
    for split in ("train", "val", "test"):
        for img in (out / "images" / split).glob("*.jpg"):
            assert (out / "labels" / split / (img.stem + ".txt")).exists()


def test_prepare_is_deterministic(tmp_path):
    src = tmp_path / "src"
    write_source(src, [(f"i{i}", make_pattern_image(i), GOOD) for i in range(20)])
    r1 = prepare({"s": src}, tmp_path / "o1", ["pothole"], seed=5)
    r2 = prepare({"s": src}, tmp_path / "o2", ["pothole"], seed=5)
    assert r1.per_split == r2.per_split
