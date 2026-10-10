import hashlib
import json
import pytest
from guide2build.engine.geometry import merge_verified_cache_receipts


def test_selected_closure_keeps_unused_verified_seed_receipts(tmp_path):
    shared, private = tmp_path / "shared", tmp_path / "private"
    shared.mkdir()
    (private / "parts").mkdir(parents=True)
    data = b"individual part test fixture"
    (private / "parts/3022.dat").write_bytes(data)
    record = {"url": "https://library.ldraw.org/library/official/parts/3022.dat",
              "sha256": hashlib.sha256(data).hexdigest()}
    (shared / "provenance.json").write_text(json.dumps({"resources": {"parts/3022.dat": record},
                                                       "file_map": {"3022.dat": "parts/3022.dat"}}))
    (private / "provenance.json").write_text('{"resources":{},"file_map":{}}')
    assert "parts/3022.dat" in merge_verified_cache_receipts(private, shared)["resources"]
    (private / "provenance.json").write_text('{"resources":{},"file_map":{}}')
    (private / "parts/3022.dat").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        merge_verified_cache_receipts(private, shared)


def test_part_context_includes_verified_asymmetric_subpart_and_rejects_tampering(tmp_path):
    from guide2build.engine.geometry import individual_catalogue_context
    resources = {}
    fixtures = {
        'parts/1.dat': ('Part', b'0 wrapper\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 s/1s01.dat\n', ['parts/s/1s01.dat']),
        'parts/s/1s01.dat': ('Subpart', b'0 asymmetric shape\n3 16 -10 0 10 10 0 10 -10 0 -10\n', []),
    }
    for name, (kind, data, dependencies) in fixtures.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        resources[name] = {'classification': kind, 'sha256': hashlib.sha256(data).hexdigest(),
            'url': 'https://library.ldraw.org/library/official/' + name, 'dependencies': dependencies}
    (tmp_path / 'provenance.json').write_text(json.dumps({'resources': resources}))
    full = individual_catalogue_context(tmp_path)[0]
    assert full['subpart_definitions'][0]['raw_ldraw_subpart_geometry'] == fixtures['parts/s/1s01.dat'][1].decode()
    bounded = individual_catalogue_context(tmp_path, max_bytes=len(fixtures['parts/1.dat'][1]))[0]
    assert bounded['subpart_definitions'] == [] and bounded['subparts_truncated']
    (tmp_path / 'parts/s/1s01.dat').write_bytes(b'tampered asymmetric shape')
    with pytest.raises(ValueError, match='hash'):
        individual_catalogue_context(tmp_path)


def test_stud_landmarks_compose_group_transforms_and_verify_hashes(tmp_path):
    from guide2build.engine.geometry import individual_catalogue_context, stud_mesh_frames
    fixtures = {
        'parts/1.dat': ('Part', b'0 fixture\n1 16 0 8 -10 0 0 -1 0 1 0 1 0 0 stug-test.dat\n', ['p/stug-test.dat']),
        'p/stug-test.dat': ('Primitive', b'0 group\n1 16 -10 0 0 1 0 0 0 1 0 0 0 1 stud.dat\n1 16 10 0 0 1 0 0 0 1 0 0 0 1 stud.dat\n', ['p/stud.dat']),
        'p/stud.dat': ('Primitive', b'0 fixture stud\n', []),
    }
    records = {}
    for path, (kind, data, dependencies) in fixtures.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        records[path] = {'classification': kind, 'sha256': hashlib.sha256(data).hexdigest(),
                        'url': 'https://library.ldraw.org/library/official/' + path, 'dependencies': dependencies}
    manifest = {'resources': records, 'file_map': {'stug-test.dat': 'p/stug-test.dat', 'stud.dat': 'p/stud.dat'}}
    (tmp_path / 'provenance.json').write_text(json.dumps(manifest))
    context = individual_catalogue_context(tmp_path)[0]
    assert [frame['position_ldu'] for frame in context['stud_mesh_frames']] == [[0, -8, 20], [0, -8, 0]]
    assert context['stud_mesh_frames'][0]['basis'] == [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
    assert not context['stud_mesh_frames_truncated']
    frames, truncated = stud_mesh_frames('parts/1.dat', manifest, lambda path, _: (tmp_path / path).read_bytes(), limit=1)
    assert len(frames) == 1 and truncated
    (tmp_path / 'p/stud.dat').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash'):
        individual_catalogue_context(tmp_path)
