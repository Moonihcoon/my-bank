"""리서치 이어받기 전용 실행 (평일 12:30 자동 실행용)
- 아침 업데이트·분봉 받기가 돌고 있으면(work\\running.lock) 끝날 때까지 기다립니다.
- 네이버 리서치를 최대 RESEARCH_MINUTES(기본 40분) 동안 이어서 받고, 분봉 자료를 만들고, GitHub에 올립니다.
- 시세 받기·통계 계산은 하지 않습니다.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE), str(PIPE / 'analysis')]
os.environ.setdefault('RESEARCH_MINUTES', '40')
from common import work_dir, log  # noqa: E402
import run_all  # noqa: E402


def main():
    lock = work_dir() / 'running.lock'
    waited = 0
    while lock.exists() and time.time() - lock.stat().st_mtime < 3 * 3600 and waited < 3 * 3600:
        time.sleep(60)
        waited += 60
    lock.write_text(time.strftime('%Y-%m-%d %H:%M'))
    try:
        log('===== 리서치 이어받기 시작 =====')
        run_all.step('코드 받기', run_all.pull)
        import research_naver
        run_all.step('네이버 리서치', research_naver.main)
        import minute_export
        run_all.step('분봉 내보내기(리서치 차트)', minute_export.main)
        run_all.step('업로드', run_all.push)
        import rebuild_rank
        run_all.step('상승률 200 올리기', rebuild_rank.main)
        log('===== 리서치 이어받기 끝 =====')
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


if __name__ == '__main__':
    main()
