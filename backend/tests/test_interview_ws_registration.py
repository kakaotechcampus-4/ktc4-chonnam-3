"""fixture의 대체 등록 없이 실제 앱의 면접 WS 진입점을 검사한다."""

from starlette.routing import WebSocketRoute

from app.core.config import Settings
from app.features.interview.ws import interview_socket
from app.main import create_app


def test_actual_app_registers_interview_websocket():
    app = create_app(Settings(_env_file=None))
    routes = [
        route
        for route in app.routes
        if isinstance(route, WebSocketRoute) and route.path == "/api/ws/interviews/{session_id}"
    ]
    assert len(routes) == 1
    assert routes[0].endpoint is interview_socket
