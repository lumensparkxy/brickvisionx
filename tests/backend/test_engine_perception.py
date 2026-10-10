"""Synthetic geometry/images verify evidence handling, never booklet accuracy."""
import hashlib
import json

from PIL import Image, ImageChops, ImageDraw
import pytest

from guide2build.engine.perception import (
    PartObservation, _part_triangles, compare_masked_images, compare_source_render_images,
    crop_callout, prepare_part_evidence, render_individual_candidate, source_relevant_catalogue,
)


@pytest.fixture
def geometry(tmp_path):
    root = tmp_path / "geometry"
    fixtures = {
        "parts/1.dat": ("Part", "Brick 2 x 2", b"0 synthetic unrelated cube description\n3 16 0 0 0 10 0 0 0 -10 0\n", []),
        "parts/999.dat": ("Part", "Slope Curved Inverted 1 x 4", b"0 synthetic asymmetric wrapper\n1 16 3 4 5 1 0 0 0 1 0 0 0 1 s/test.dat\n", ["parts/s/test.dat"]),
        "parts/s/test.dat": ("Subpart", "Synthetic triangle", b"0 original asymmetric test triangle\n3 16 0 0 0 30 0 0 0 -8 -17\n", []),
    }
    records = {}
    for name, (classification, description, data, deps) in fixtures.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records[name] = {"classification": classification, "description": description,
                         "url": "https://library.ldraw.org/library/official/"+name,
                         "sha256": hashlib.sha256(data).hexdigest(), "dependencies": deps}
    material = b"0 Original synthetic material fixture; no download\n"
    (root / "LDConfig.ldr").write_bytes(material)
    (root / "provenance.json").write_text(json.dumps({"resources": records,
        "file_map": {"s/test.dat": "parts/s/test.dat"},
        "materials": {"LDConfig.ldr": {"url": "https://library.ldraw.org/library/official/LDConfig.ldr",
                                       "sha256": hashlib.sha256(material).hexdigest()}}}))
    return root


def observation():
    return {"observation_id": "callout-1", "source": {"source_sha256": "a"*64, "page_index": 0, "bbox": [.25, .25, .75, .75]},
            "quantity": 2, "shape_cues": ["curved inverted slope 1 x 4"], "colour_description": "apparent white",
            "candidates": [{"part_id": "999", "reason": "Synthetic shape cue match", "color_codes": ["15"]}],
            "uncertainties": ["Identity is a candidate, not a reviewed observation."]}


def test_shape_relevant_retrieval_precedes_file_order_and_budget(geometry):
    result = source_relevant_catalogue(geometry, shape_cues=["curved inverted slope 1 x 4"], max_parts=1, max_bytes=1000)
    assert result["parts"][0]["part_id"] == "999"
    assert "curve" in result["parts"][0]["matched_shape_terms"]
    assert result["retrieval"]["candidate_count"] == 2
    explicit = source_relevant_catalogue(geometry, shape_cues=["curved slope"], part_ids=["1"], max_parts=1)
    assert explicit["parts"][0]["part_id"] == "1"


def test_actual_individual_triangles_preserve_subpart_transform_and_single_axis_conversion(geometry, tmp_path):
    triangles, pins = _part_triangles(geometry, "999")
    assert triangles == [[(3., -4., -5.), (33., -4., -5.), (3., 4., 12.)]]
    assert set(pins) == {"parts/999.dat", "parts/s/test.dat"}
    receipt = render_individual_candidate("999", geometry, tmp_path / "render")
    image = Image.open(receipt["path"])
    assert image.size == (576, 214)
    assert receipt["triangle_count"] == 1
    assert ImageChops.difference(image.crop((0, 0, 192, 192)), Image.new("RGB", (192, 192), "white")).getbbox()
    assert receipt["renderer"] == "individual-triangle-painter-v1"
    assert hashlib.sha256((tmp_path / "render/part-999-views.png").read_bytes()).hexdigest() == receipt["sha256"]


def test_source_crop_and_candidate_images_have_hash_receipts_and_immutable_replay(geometry, tmp_path):
    pages, output = tmp_path / ("a"*64), tmp_path / "evidence"
    pages.mkdir()
    page = Image.new("RGB", (128, 64), "white")
    ImageDraw.Draw(page).rectangle((32, 16, 95, 47), fill="red")
    page.save(pages / "page-000.png")
    result = prepare_part_evidence([observation()], pages, geometry, output)
    assert len(result["image_paths"]) == 2 and not result["findings"]
    crop = result["observations"][0]["callout"]
    assert crop["pixel_bbox"] == [32, 16, 96, 48]
    assert Image.open(crop["path"]).getpixel((10, 10)) == (255, 0, 0)
    assert prepare_part_evidence([observation()], pages, geometry, output)["receipt"] == result["receipt"]
    page.putpixel((40, 20), (0, 0, 0))
    page.save(pages / "page-000.png")
    with pytest.raises(ValueError, match="immutable"):
        prepare_part_evidence([observation()], pages, geometry, output)


def test_bad_candidates_source_identity_and_asset_tampering_are_not_silent(geometry, tmp_path):
    value = observation()
    value["candidates"] *= 4
    with pytest.raises(ValueError):
        PartObservation.model_validate(value)
    with pytest.raises(ValueError, match="source PDF hash"):
        crop_callout(observation(), tmp_path / "wrong", tmp_path / "out")
    (geometry / "parts/s/test.dat").write_text("tampered")
    with pytest.raises(ValueError, match="hash"):
        render_individual_candidate("999", geometry, tmp_path / "out")


def test_finished_model_dependency_is_rejected_even_if_bytes_are_pinned(geometry, tmp_path):
    manifest = json.loads((geometry / "provenance.json").read_text())
    manifest["resources"]["parts/s/test.dat"]["classification"] = "Model"
    (geometry / "provenance.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="allowed part"):
        render_individual_candidate("999", geometry, tmp_path / "out")


def mask(path, box):
    image = Image.new("L", (128, 96), 0)
    ImageDraw.Draw(image).rectangle(box, fill=255)
    image.save(path)


def test_explicit_masks_rank_aligned_shape_over_wrong_position_and_blank_is_not_success(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    Image.new("RGB", (128, 96), "white").save(source)
    Image.new("RGB", (128, 96), "white").save(render)
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    mask(a, (20, 15, 60, 70))
    mask(b, (20, 15, 60, 70))
    exact = compare_masked_images(source, render, a, b)
    assert exact["ranking_score"] == pytest.approx(1)
    mask(b, (60, 15, 100, 70))
    wrong = compare_masked_images(source, render, a, b)
    assert wrong["ranking_score"] < exact["ranking_score"]
    Image.new("L", (128, 96), 0).save(b)
    assert compare_masked_images(source, render, a, b)["status"] == "insufficient"
    Image.new("L", (128, 96), 255).save(a)
    Image.new("L", (128, 96), 255).save(b)
    full = compare_masked_images(source, render, a, b)
    assert full["ranking_score"] is full["silhouette_iou"] is None
    assert "Near-full" in full["reason"]


def test_source_camera_comparison_retains_masks_and_exclusions_without_certifying_them(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    image = Image.new("RGB", (128, 96), "white")
    ImageDraw.Draw(image).polygon([(20, 20), (90, 20), (40, 80)], fill="blue")
    image.save(source)
    image.save(render)
    report = compare_source_render_images(source, render, [0, 0, 1, 1], tmp_path / "comparison",
        render_source_rect={"x": 0, "y": 0, "width": 128, "height": 96}, excluded_source_boxes=[[0, 0, .1, .1]],
        camera_registration=registration(render))
    assert report["ranking_score"] == pytest.approx(1)
    assert not report["mask_policy"]["human_reviewed"]
    assert report["rank_eligible"]
    assert len(report["images"]) == 7
    assert any("white/transparent" in limit for limit in report["limitations"])
    with pytest.raises(ValueError, match="outside"):
        compare_source_render_images(source, render, [0, 0, 1, 1], tmp_path / "bad",
            render_source_rect={"x": 100, "y": 0, "width": 128, "height": 96})


def registration(path):
    with Image.open(path) as image:
        width, height = image.size
    return {"version": "source-render-registration-v1", "status": "registered",
        "render_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "screenshot_size": [width, height],
        "render_source_rect": {"x": 0, "y": 0, "width": width, "height": height}}


def painted(path, background, *, offset=0, foreground="white", box=(30, 24, 90, 70)):
    image = Image.new("RGB", (128, 96), background)
    if box is not None:
        a, b, c, d = box
        ImageDraw.Draw(image).rectangle((a+offset, b, c+offset, d), fill=foreground)
    image.save(path)


def compare(source, rendered, output, *, exclusions=(), box=(0, 0, 1, 1), registered=True):
    reg = registration(rendered)
    return compare_source_render_images(source, rendered, box, output,
        render_source_rect=reg["render_source_rect"], excluded_source_boxes=exclusions,
        camera_registration=reg if registered else None)


def test_coloured_backgrounds_are_removed_while_white_piece_interior_is_retained(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252))
    painted(render, (237, 242, 247))
    result = compare(source, render, tmp_path / "comparison")
    assert result["rank_eligible"]
    assert result["silhouette_iou"] == pytest.approx(1)
    assert result["edge_f1"] == pytest.approx(1)
    assert result["mask_policy"]["version"] == "border-connected-background-v1"
    for side, background in [("source", [212, 237, 252]), ("render", [237, 242, 247])]:
        checks = result["segmentation_checks"][side]
        assert checks["background_rgb"] == background
        assert checks["foreground_fraction"] == pytest.approx(61*47/(128*96))
        with Image.open(result["images"][side+"-mask"]["path"]) as mask:
            assert mask.getpixel((50, 50)) == 255
            assert mask.getpixel((10, 10)) == 0
    assert result["segmentation_checks"]["comparability"]["automatic_checks_only"]


def test_changed_geometry_lowers_score_without_changing_source_comparison_scope(tmp_path):
    source, aligned, displaced = [tmp_path / name for name in ["source.png", "aligned.png", "displaced.png"]]
    painted(source, (212, 237, 252))
    painted(aligned, (237, 242, 247))
    painted(displaced, (237, 242, 247), offset=20)
    exact = compare(source, aligned, tmp_path / "aligned")
    wrong = compare(source, displaced, tmp_path / "displaced")
    assert wrong["rank_eligible"]
    assert wrong["ranking_score"] < exact["ranking_score"]
    assert wrong["silhouette_iou"] < .6
    assert exact["comparison_scope_sha256"] == wrong["comparison_scope_sha256"]
    assert exact["camera_registration_sha256"] != wrong["camera_registration_sha256"]


@pytest.mark.parametrize("kind", ["background_only", "near_full", "low_contrast", "nonuniform_border", "clipped"])
def test_ambiguous_or_uninformative_masks_are_unscorable(tmp_path, kind):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252))
    painted(render, (237, 242, 247))
    if kind == "background_only":
        painted(source, (212, 237, 252), box=None)
    elif kind == "near_full":
        painted(source, (212, 237, 252), box=(3, 3, 124, 92))
    elif kind == "low_contrast":
        painted(source, (212, 237, 252), foreground=(217, 237, 252))
    elif kind == "clipped":
        painted(source, (212, 237, 252), box=(0, 24, 90, 70))
    else:
        image = Image.open(source)
        ImageDraw.Draw(image).rectangle((0, 0, 63, 95), fill=(80, 120, 150))
        image.save(source)
    result = compare(source, render, tmp_path / "comparison")
    assert result["status"] == "unscorable"
    assert not result["rank_eligible"]
    assert result["ranking_score"] is result["silhouette_iou"] is result["edge_f1"] is None
    assert result["segmentation_checks"]["source"]["reasons"]
    assert result["segmentation_checks"]["comparability"]["status"] == "unscorable"


def test_unexcluded_callout_is_ambiguous_and_explicit_common_exclusion_is_recorded(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252), box=(60, 35, 100, 75))
    painted(render, (237, 242, 247), box=(60, 35, 100, 75))
    image = Image.open(source)
    ImageDraw.Draw(image).rectangle((8, 8, 38, 25), fill=(178, 215, 243), outline="black")
    image.save(source)
    contaminated = compare(source, render, tmp_path / "contaminated")
    assert not contaminated["rank_eligible"]
    assert "Multiple substantial" in contaminated["reason"]
    excluded = compare(source, render, tmp_path / "excluded", exclusions=[[.02, .02, .35, .30]])
    assert excluded["ranking_score"] == pytest.approx(1)
    assert excluded["comparison_scope_sha256"] != contaminated["comparison_scope_sha256"]
    assert excluded["segmentation_checks"]["comparability"]["shared_exclusion_mask"]
    assert excluded["mask_policy"]["excluded_source_boxes"] == [[.02, .02, .35, .30]]


def test_pixel_shape_does_not_substitute_for_camera_registration(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252))
    painted(render, (237, 242, 247))
    result = compare(source, render, tmp_path / "comparison", registered=False)
    assert not result["rank_eligible"]
    assert result["ranking_score"] is None
    assert "registration is required" in result["reason"]


@pytest.mark.parametrize("key,value", [("render_sha256", "0"*64), ("screenshot_size", [128, 95]),
    ("render_source_rect", {"x": 0, "y": 0, "width": 127, "height": 96})])
def test_registration_integrity_mismatch_is_hard_not_an_unscorable_mask(tmp_path, key, value):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252))
    painted(render, (237, 242, 247))
    reg = registration(render)
    rect = reg["render_source_rect"]
    reg[key] = value
    with pytest.raises(ValueError, match="registration .* changed"):
        compare_source_render_images(source, render, [0, 0, 1, 1], tmp_path / "comparison",
            render_source_rect=rect, camera_registration=reg)


def test_comparison_scope_binds_source_crop_exclusions_and_deterministic_replay(tmp_path):
    source, render = tmp_path / "source.png", tmp_path / "render.png"
    painted(source, (212, 237, 252))
    painted(render, (237, 242, 247))
    original = compare(source, render, tmp_path / "comparison")
    assert compare(source, render, tmp_path / "comparison") == original
    cropped = compare(source, render, tmp_path / "cropped", box=(.02, .02, .98, .98))
    assert cropped["rank_eligible"]
    assert cropped["comparison_scope_sha256"] != original["comparison_scope_sha256"]
    excluded = compare(source, render, tmp_path / "excluded", exclusions=[[0, 0, .1, .1]])
    assert excluded["rank_eligible"]
    assert excluded["comparison_scope_sha256"] != original["comparison_scope_sha256"]
    painted(source, (211, 237, 252))
    replaced = compare(source, render, tmp_path / "replaced")
    assert replaced["comparison_scope_sha256"] != original["comparison_scope_sha256"]
    with pytest.raises(ValueError, match="immutable"):
        compare(source, render, tmp_path / "comparison")
