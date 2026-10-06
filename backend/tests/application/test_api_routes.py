from color_rush.api.app import create_app


def test_health_and_versioned_routes_registered() -> None:
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/overlay" in paths
    assert "/api/v1/overlay/ws-ticket" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/refresh" in paths
    assert "/api/v1/admin/rounds/start" in paths
    assert "/api/v1/admin/games" in paths
    assert "/api/v1/admin/sessions" in paths
    assert "/api/v1/admin/source" in paths
    assert "/api/v1/admin/youtube/oauth/start" in paths
    assert "/api/v1/admin/youtube/oauth/callback" in paths
    assert "/api/v1/admin/users" in paths
    assert "/api/v1/periods/{period_id}/champions" in paths
    assert "/api/v1/periods/{period_id}/archives" in paths
    assert "/simulation/commands" in paths
    assert "/simulation/commands/batch" in paths
    assert "/metrics" in paths
    assert "/api/v1/admin/projections/rebuild" in paths
    from color_rush.api.ws import ws_router

    included = {getattr(route, "path", "") for route in ws_router.routes}
    assert "/ws/v1/overlay" in included
    assert "/ws/v1/admin" in included
