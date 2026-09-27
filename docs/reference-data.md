# Municipality reference data

`services/*/src/airmax_*/reference/municipalities.geojson` (identical copies in transformation and
website, enforced by `tests/test_reference_data.py`) hold the boundaries of all 565
Belgian municipalities (WGS84, simplified), with properties `nis_code`, `name_nl`, `name_fr` and
`name_de`. The source is the Belgian National Geographic Institute's NGI/IGN AdminVector dataset, catalogue ID
[`fb1e2993-2020-428c-9188-eb5f75e284b9`](https://www.geo.be/catalog/details/fb1e2993-2020-428c-9188-eb5f75e284b9?l=en),
EPSG:4326 snapshot dated 2026-07-16. The checked-in simplified GeoJSON is approximately 1.6 MB;
`tests/test_reference_data.py` verifies that both service copies remain byte-identical.

Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Attribution: **Boundaries © NGI/IGN, CC BY 4.0**.

Each municipality is shown in its own language: Dutch in Flanders, French in Wallonia, German in
the nine German-speaking municipalities, and French / Dutch in Brussels (so Liège, not Luik). The
rule lives in `local_name` (transformation) and `municipalityName` (website `app.js`).

Transformation loads these 565 geometries into a Shapely spatial index; measurement records stream
through temporary files rather than accumulating in memory.
