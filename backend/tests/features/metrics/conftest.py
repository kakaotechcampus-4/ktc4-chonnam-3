"""지표 쿼리 테스트는 면접 테스트의 PostgreSQL fixture 를 그대로 쓴다.

task-17
"""

from tests.features.interview.conftest import db, test_database_url

__all__ = ["db", "test_database_url"]
