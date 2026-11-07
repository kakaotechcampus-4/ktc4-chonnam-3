"""fixture의 대체 등록 없이 실제 앱의 면접 WS 진입점을 검사한다."""

from starlette.routing import Match

from app.core.config import Settings
from app.features.interview.ws import interview_socket
from app.main import create_app


def test_actual_app_registers_interview_websocket():
    app = create_app(Settings(_env_file=None))
    session_id = "00000000-0000-0000-0000-000000000001"
    path = f"/api/ws/interviews/{session_id}"
    scope = {"type": "websocket", "path": path, "root_path": ""}
    routes = [route for route in app.routes if route.matches(scope)[0] == Match.FULL]
    assert len(routes) == 1
    assert str(app.url_path_for(interview_socket.__name__, session_id=session_id)) == path
