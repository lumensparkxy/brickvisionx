# Synthetic fixtures
`synthetic.scene.json` is an original two-instance contract fixture, not a LEGO set or a buildable model.
Its source hash describes the fixture identity string, not an official PDF. Geometry is deliberately absent.
Never load this as set 30669, use it in a target-model screenshot, or cite it as reconstruction evidence.

`synthetic-white-page.png` (32x24 white), `synthetic-white-tile.png` (16x16 white)
and `synthetic-red-frame.png` (16x16 red) are original synthetic test pixels. Their
exact PNG bytes are frozen because prompt regression tests hash their source/render
receipts. Regenerating identical pixels with a different PNG encoder can change the
compressed bytes. These files contain no official booklet or part-library content.
