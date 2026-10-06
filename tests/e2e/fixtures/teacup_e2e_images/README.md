# Synthetic Teacup E2E Page Images

These ten JPEG pages are AI-generated test fixtures. They contain placeholder
text, schematic stone-tool figures, captions, tables, and page numbers; they do
not reproduce source publication pages.

The five `a4_` images are portrait pages. The five `a3_` images are landscape
pages. Nine files use deliberately low JPEG quality to keep the fixture small;
`a4_01_page_147.jpg` retains moderate quality as a detailed rendering sample.

`tests/e2e/fixtures/tiny_source_project/` contains byte-identical copies of one
A3 and one A4 page for migration and GUI replay tests. Keep those copies and
their `annotations.json` records synchronized when replacing either file.
