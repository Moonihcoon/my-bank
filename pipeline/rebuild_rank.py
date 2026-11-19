"""'상승률 200' 화면만 다시 만들어 공유 저장소에 올립니다(통계 재계산·시세 받기 없음, 1~2분).
화면 템플릿(web_src)만 바뀌었을 때 씁니다."""
from __future__ import annotations
import os, runpy, shutil, sys
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path[:0] = [str(PIPE), str(PIPE / 'analysis')]
from common import work_dir, log  # noqa: E402
import run_all  # noqa: E402


def main():
    w = work_dir()
    web = w / 'web'
    for sub in ('data', 'px'):
        (web / sub).mkdir(parents=True, exist_ok=True)
    for f in (PIPE / 'web_src').iterdir():
        shutil.copy(f, web / f.name)
    cwd = os.getcwd()
    os.chdir(w)
    try:
        runpy.run_path(str(PIPE / 'analysis' / 'build_top.py'), run_name='__main__')
    finally:
        os.chdir(cwd)
    log('상승률 200 화면 다시 만들기 완료')
    run_all.publish_share()


if __name__ == '__main__':
    main()
