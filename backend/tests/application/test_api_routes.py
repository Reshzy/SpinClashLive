from color_rush.api.app import create_app


def test_health_and_simulation_routes_registered() -> None:
    app = create_app()
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/simulation/commands" in paths
    assert "/simulation/rounds/start" in paths
