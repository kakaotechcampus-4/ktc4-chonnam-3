"""users upsert + github_accounts upsert. 트랜잭션 경계.
★ 토큰은 core/crypto.py 로 암호화해 BYTEA 에 넣는다. 평문 저장 금지.
★ 연동 직후 initial_sync(M1) 를 enqueue 한다.
★ users.status가 suspended / withdrawn이면 각각 403 account_suspended /
  account_withdrawn으로 로그인을 막는다. 실제 인증 연결은 구현 대기다.

확정본 §1 / task-06
"""
