from physics_atlas_api.main import create_app


def test_product_rename_preserves_api_routes() -> None:
    schema = create_app().openapi()

    assert schema["info"]["title"] == "Atlas Physica API"
    assert (
        "developed and maintained by Tech Echo Collective"
        in schema["info"]["description"]
    )
    assert "/api/health" in schema["paths"]
    assert "/api/metric-observations" in schema["paths"]
