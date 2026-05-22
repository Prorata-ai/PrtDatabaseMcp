from prt_database_mcp.catalog import search_catalog


def test_search_catalog_hits_publishers():
    catalog = {
        "tables": {
            "publishers": {
                "service": "PrtPublisherPortal",
                "schema": "public",
                "description": "Publisher accounts",
            }
        }
    }
    hits = search_catalog(catalog, "publisher")
    assert hits
    assert hits[0]["table"] == "publishers"
