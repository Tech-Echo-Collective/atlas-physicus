# Geographic representation policy

## Purpose

Physics Atlas visualizes scientific activity across geography. It does not interpret, endorse, or adjudicate political boundaries, sovereignty, or territorial claims.

Map geometry provides geographic context for exploration. A rendered boundary must not be read as a statement about political status, and the visual prominence of a place must not be read as a measure of scientific quality.

## Separate geographic and scientific layers

Physics Atlas treats geographic rendering and research attribution as separate layers:

1. the geographic layer renders places, boundaries, and research locations from documented map sources;
2. the research layer connects institutions, affiliations, researchers, and scientific activity using source metadata;
3. visualization components join those layers for exploration without converting map geometry into ownership of scientific work.

This separation allows geographic source data to change without redefining scientific attribution, and allows research metadata to improve without embedding political logic in the map.

## Institution and affiliation attribution

Institutions are assigned to research locations using documented institutional metadata, including their physical coordinates and address information. Scientific contribution follows the affiliations recorded for the contributing researchers or organizations.

A collaborative paper is attributed to every participating institution represented by its affiliation metadata. For example, if Institutions A, B, and C contribute, each receives attribution. Physics Atlas does not force the paper into a single-institution or single-country ownership model.

Country-level views may aggregate affiliated activity for exploration, but those aggregates remain multi-attribution summaries. They do not imply exclusive national ownership of collaborative science.

## Special research locations

- CERN is represented at its physical research location. Scientific contribution associated with CERN work follows the participating institutional affiliations recorded in the source metadata.
- Polar research stations are treated as research locations. Their scientific contribution follows institution and affiliation metadata rather than being inferred from surrounding map geometry.

These are applications of the general location-and-affiliation rules, not hardcoded geopolitical exceptions.

## Geographic view membership

The frontend uses validated `GeographicView` records to connect an exploration canvas to one or more source geometries and institution-location entities. This is a general mapping layer rather than conditionals inside map components. An institution is included when its unchanged `countryId` location metadata belongs to the selected view; its affiliations and research relationships are not rewritten.

For the current requested prototype behavior, the China exploration configuration contains source geometry identifiers `156` and `158` and location entities `country-cn` and `country-tw`. Consequently, the complete configured canvas and institutions located in Taiwan appear while exploring the China view. This configuration controls map membership only. It does not merge entity identity, alter research attribution, or express scientific or political ownership.

The packaged `world-atlas` source preserves `156` as a renderable MultiPolygon and `158` as a renderable Polygon. The application does not simplify or reconstruct either feature. Country mode composes every configured polygon into a dedicated exploration-canvas GeoJSON source. That source drives the fill, outline, glow, and camera fit independently from the world choropleth, ensuring that all configured geometry remains visibly present.

In World View, heatmap color is also resolved through geographic-view membership. Every source geometry in a view receives the display metric value supplied for that view's country entity. Native location identity remains unchanged—for example, geometry `158` retains `country-tw` as its location entity while using `country-cn` as its configured visualization metric entity. This is a presentation join only and does not create, duplicate, or reassign metric observations.

Unconfigured source geometries fall back to direct ISO-numeric matching. Future geographic source changes should be handled by updating validated mapping data and provenance, not by adding one-off rendering patches.

## Implementation requirements

- Do not hardcode individual territorial or geopolitical exceptions in product components or metric logic.
- Preserve source provenance for geographic geometry, institution locations, and affiliations.
- Keep missing or ambiguous metadata explicit rather than assigning ownership from map position alone.
- Permit multiple institutional and geographic attributions when supported by affiliation records.
- Describe rendered activity as scientific exploration data, never as political ownership or a scientific ranking.

v3.0.2-alpha retains the synthetic location fixture and also provides a bounded INSPIRE-HEP metadata pilot. Changing the source, displayed metric, or user-defined weight profile does not alter geographic membership, attribution, affiliations, or entity relationships. Pilot country participation is derived from resolved institution-affiliation metadata, not from map geometry, and each collaborative paper is fully attributed to every resolved participating location. The pilot is incomplete and does not establish authoritative historical geography or contribution shares.
