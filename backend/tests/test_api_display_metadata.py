from physics_atlas_api.main import create_app


def test_product_rename_preserves_api_routes() -> None:
    schema = create_app().openapi()

    assert schema["info"]["title"] == "Atlas Physicus API"
    assert (
        "Part of Tech Echo Physica, a Tech Echo Collective project family"
        in schema["info"]["description"]
    )
    assert "/api/health" in schema["paths"]
    assert "/api/metric-observations" in schema["paths"]
