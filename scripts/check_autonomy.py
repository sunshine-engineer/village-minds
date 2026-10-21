"""Verify six villagers act concurrently in a temporary native game session."""
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from village.game import VillageGame
from village.simulation import distance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true',help='Check without any model connection')
    parser.add_argument('--headless',action='store_true',help='Render offscreen without taking desktop focus')
    parser.add_argument('--wait-for-model',action='store_true',help='Also require one accepted real model plan within 100 seconds')
    args=parser.parse_args()
    if args.headless:
        from panda3d.core import loadPrcFileData
        loadPrcFileData('autonomy-check','window-type offscreen\nback-buffers 0\nclock-mode limited\nclock-frame-rate 20')
    app=VillageGame(SimpleNamespace(demo=args.demo,no_save=True,smoke_test=False,
        url='http://localhost:11434',model='qwen2.5:1.5b',pace=1))
    starts=[bot.position for bot in app.world.villagers]
    maximum=[0.0]*len(starts)
    def finish(task):
        for i,bot in enumerate(app.world.villagers):
            maximum[i]=max(maximum[i],distance(starts[i],bot.position))
        if task.time<5:
            return task.cont
        assert all(moved>.5 for moved in maximum), maximum
        if args.wait_for_model and not app.brains.model_decisions:
            if task.time>=100:
                raise AssertionError('No accepted model plan: '+app.brains.status)
            return task.cont
        report={'passed':'all six villagers moved without waiting for a model turn',
            'backend':app.brains.status, 'local_decisions':app.brains.local_decisions,
            'accepted_model_decisions':app.brains.model_decisions,
            'seconds':round(task.time,2),
            'villagers':[{'name':b.name,'action':b.action,'max_distance_from_start':round(moved,2)}
                          for b,moved in zip(app.world.villagers,maximum)]}
        out=Path('artifacts'); out.mkdir(exist_ok=True)
        suffix=('windows' if sys.platform=='win32' else 'linux') + ('-model' if args.wait_for_model else '')
        (out/f'autonomy-{suffix}.json').write_text(json.dumps(report,indent=2))
        app.win.saveScreenshot(str(out/f'autonomy-{suffix}.png'))
        print(json.dumps(report,indent=2),flush=True)
        app.taskMgr.stop()
        return task.done
    app.taskMgr.add(finish,'concurrent-autonomy-check')
    try:app.run()
    finally:app.destroy()


if __name__=='__main__':
    main()
